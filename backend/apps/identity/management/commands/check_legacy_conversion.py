"""Pré-vol en lecture seule de la conversion des comptes entreprise (L0-09 T9-1, spec T9 §2.2).

À lancer AVANT `migrate` sur une copie ou sur la base de développement. Ne modifie rien. N'affiche que des
identifiants (UUID) et des comptages : jamais de nom, de NIF, d'e-mail ni de téléphone (règle 10), car la sortie est
copiée dans des tickets. Aucune anomalie n'est bloquante (tout est corrigé par la règle de conversion ou signalé au
personnel) : code de sortie 0 ; 1 seulement si une table attendue manque.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import connection

from apps.identity import legacy_conversion as rules
from apps.identity.models import (
    BusinessProfile, BusinessProfileCategory, KycDocument, LegacyAccountMapping, Organization,
    OrganizationDocumentRequirement, User, kyc_storage,
)
from apps.moderation.services import get_restricted_user_ids

LIST_LIMIT = 100
EXPECTED_TABLES = (
    BusinessProfile, BusinessProfileCategory, KycDocument, LegacyAccountMapping, Organization,
    OrganizationDocumentRequirement, User,
)


class Command(BaseCommand):
    help = "Pré-vol (lecture seule) de la conversion des comptes entreprise en organisations."

    def emit(self, label, ids):
        ids = sorted(str(i) for i in ids)
        self.stdout.write(f'{label}: {len(ids)}')
        if ids:
            shown = ids[:LIST_LIMIT]
            suffix = f' … (+{len(ids) - LIST_LIMIT})' if len(ids) > LIST_LIMIT else ''
            self.stdout.write('  ' + ', '.join(shown) + suffix)

    def handle(self, *args, **options):
        existing = set(connection.introspection.table_names())
        missing = [m._meta.db_table for m in EXPECTED_TABLES if m._meta.db_table not in existing]
        if missing:
            self.stderr.write(f"Table(s) manquante(s) : {', '.join(missing)}")
            raise SystemExit(1)

        mapped_users = set(LegacyAccountMapping.objects.values_list('user_id', flat=True))
        profiles = list(BusinessProfile.objects.select_related('user').order_by('created_at', 'pk'))
        todo = [p for p in profiles if p.user_id not in mapped_users]
        self.stdout.write(f'profils: {len(profiles)}')
        self.stdout.write(f'profils déjà convertis (correspondance): {len(profiles) - len(todo)}')
        self.stdout.write(f'profils à convertir: {len(todo)}')
        self.emit(
            "comptes ENTREPRISE sans profil (non convertis)",
            User.objects.filter(user_type='ENTREPRISE', business_profile__isnull=True).values_list('pk', flat=True),
        )
        self.stdout.write(f"profils dont le type d'organisation sera ENTREPRISE par défaut: {len(todo)}")

        self.emit("noms vides ou trop courts après nettoyage (nom neutre)",
                  [p.pk for p in todo if rules.needs_neutral_name(p.business_name)])
        self.emit("noms de plus de 255 caractères après nettoyage (tronqués)",
                  [p.pk for p in todo if len(' '.join((p.business_name or '').split())) > rules.NAME_MAX_LENGTH])
        self.emit("noms mélangeant latin, cyrillique et grec (conservés)",
                  [p.pk for p in todo if rules.mixes_scripts(p.business_name)])

        by_key = defaultdict(list)
        for p in todo:
            by_key[rules.name_key(rules.converted_name(p.business_name, p.pk))].append(p.pk)
        existing_orgs = defaultdict(list)
        for pk, name, legacy in Organization.objects.values_list('pk', 'name', 'legacy_business_profile_id'):
            existing_orgs[rules.name_key(name)].append(pk)
        pairs = []
        for key, ids in by_key.items():
            pairs += [f'{a}~{b}' for i, a in enumerate(ids) for b in ids[i + 1:]]
            pairs += [f'{a}~{org}' for a in ids for org in existing_orgs.get(key, [])]
        self.emit("collisions de noms (profil~profil ou profil~organisation, casse et accents ignorés)", pairs)

        by_nif = defaultdict(list)
        for p in todo:
            if (p.nif or '').strip():
                by_nif[p.nif.strip().casefold()].append(p.pk)
        self.emit("profils partageant un NIF non vide", [pk for ids in by_nif.values() if len(ids) > 1 for pk in ids])

        self.emit("descriptions de plus de 2000 caractères (tronquées)",
                  [p.pk for p in todo if len(p.bio or '') > rules.DESCRIPTION_MAX_LENGTH])
        counts = defaultdict(int)
        for pid in BusinessProfileCategory.objects.values_list('business_profile_id', flat=True):
            counts[pid] += 1
        self.emit("profils avec plus de 5 catégories (conservées)",
                  [p.pk for p in todo if counts[p.pk] > rules.MAX_CATEGORIES])

        # Vérification : jamais recopiée ; on liste les profils dont l'ancien drapeau diffère du calcul dérivé.
        required = set(OrganizationDocumentRequirement.objects.filter(org_type=rules.ORG_TYPE)
                       .values_list('document_type', flat=True))
        validated = defaultdict(set)
        for pid, doc_type in KycDocument.objects.filter(
            business_profile__isnull=False, status=KycDocument.STATUS_VALIDE,
        ).values_list('business_profile_id', 'document_type'):
            validated[pid].add(doc_type)
        self.emit("profils dont is_verified diffère du calcul dérivé des pièces (le drapeau n'est pas recopié)",
                  [p.pk for p in todo if p.is_verified != (bool(required) and required <= validated[p.pk])])

        owners = {p.user_id: p.pk for p in todo}
        self.emit("propriétaires désactivés (organisation SUSPENDED)",
                  [p.pk for p in todo if not p.user.is_active])
        restricted = get_restricted_user_ids(owners.keys())
        self.emit("propriétaires sous sanction bloquante (examen par le personnel si le compte reste actif)",
                  [owners[uid] for uid in restricted])

        missing_files, both = [], []
        for doc in KycDocument.objects.filter(business_profile__isnull=False).only(
            'pk', 'file', 'business_profile_id', 'organization_id',
        ):
            if not doc.file or not doc.file.name or not kyc_storage.exists(doc.file.name):
                missing_files.append(doc.pk)
            if doc.organization_id is not None:
                both.append(doc.pk)
        self.emit("pièces dont le fichier est absent du stockage privé", missing_files)
        self.emit("pièces déjà rattachées à une organisation ET à un profil (non réaffectées)", both)
        self.stdout.write("Pré-vol terminé : aucune donnée modifiée.")
