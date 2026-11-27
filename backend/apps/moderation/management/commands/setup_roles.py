"""CDC 3.11 : rôles super-administrateur (is_superuser, déjà géré par Django),
administrateur et modérateur (Group + permissions Django). Idempotent :
peut être relancé sans effet de bord, notamment à chaque déploiement
(docker-entrypoint.sh) : les groupes sont recalés exactement sur les tables
ci-dessous (`set`), les permissions retirées du code sont donc retirées des groupes."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

# Moindre privilège (règle 12, CDC 3.11) : seuls les modèles listés ci-dessous sont accessibles
# aux rôles. Aucun accès, volontairement, aux messages et conversations privés, aux notifications,
# aux codes OTP, aux comptes (modification) ni au module `payments` (gelé, L0-13).
# Une permission qui ne correspond à aucun modèle fait échouer la commande (faute de frappe,
# module renommé) au lieu d'être ignorée en silence.
MODERATOR_PERMISSIONS = {
    'moderation.report': ['view', 'add', 'change'],
    'moderation.sanction': ['view', 'add'],
    'catalog.forbiddenitem': ['view'],
    'identity.kycdocument': ['view', 'review'],  # review : décider et télécharger, jamais éditer à la main
    'identity.user': ['view'],  # expose e-mail et téléphone dans l'admin : finalité KYC, à valider LEG-PRV
    'reviews.review': ['view', 'change'],  # masquer un avis ; l'admin ne laisse modifier que is_hidden
    'marketplace.offer': ['view'],
}

# L'administrateur hérite de tout ce que peut faire un modérateur, plus la
# gestion des sanctions lourdes, des référentiels et des paramètres d'algorithme.
ADMINISTRATOR_EXTRA_PERMISSIONS = {
    'moderation.sanction': ['change', 'delete'],
    'catalog.forbiddenitem': ['add', 'change', 'delete'],
    # ADR 0006, 11.4 : organisations en lecture et suspension/réactivation (dont celles converties en SUSPENDED),
    # exigences de pièces et réglages modifiables ; appartenances en lecture seule (ni téléphone ni e-mail).
    'identity.organization': ['view', 'suspend'],
    'identity.membership': ['view'],
    'identity.organizationdocumentrequirement': ['view', 'add', 'change', 'delete'],
    'identity.identitysettings': ['view', 'change'],
    'catalog.category': ['add', 'change', 'delete'],
    'catalog.city': ['add', 'change', 'delete'],
    'catalog.commune': ['add', 'change', 'delete'],
    'visibility.rankingsettings': ['view', 'change'],
    'visibility.visibilitysettings': ['view', 'change'],
    'marketplace.marketplacesettings': ['view', 'change'],
    'moderation.auditlog': ['view'],  # journal en lecture seule : jamais modifiable
    'reviews.reviewsettings': ['view', 'change'],
    'moderation.moderationsettings': ['view', 'change'],
}


# Séparation des fonctions (ADR 0010 §9.1) : les décisions de vérification (levée de la revue de création ; plus tard
# nominations et niveau d'assurance, B9) relèvent du seul groupe « Vérification », distinct de l'Administrateur.
VERIFICATION_PERMISSIONS = {
    'identity.organization': ['view', '=review_organization_creation'],
}


def _permissions_for(spec):
    permissions = []
    for label, actions in spec.items():
        app_label, model = label.split('.')
        for action in actions:
            # `=codename` : permission personnalisée dont le nom ne suit pas `<action>_<modèle>`.
            codename = action[1:] if action.startswith('=') else f'{action}_{model}'
            try:
                permissions.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
            except Permission.DoesNotExist:
                raise CommandError(f"Permission inconnue : {app_label}.{codename} (migrations appliquées ?).")
    return permissions


class Command(BaseCommand):
    help = "Crée/actualise les groupes Modérateur, Administrateur et Vérification (CDC 3.11, ADR 0010 §9.1)."

    def handle(self, *args, **options):
        moderator_perms = _permissions_for(MODERATOR_PERMISSIONS)
        moderator_group, _ = Group.objects.get_or_create(name='Modérateur')
        moderator_group.permissions.set(moderator_perms)

        admin_perms = moderator_perms + _permissions_for(ADMINISTRATOR_EXTRA_PERMISSIONS)
        admin_group, _ = Group.objects.get_or_create(name='Administrateur')
        admin_group.permissions.set(admin_perms)

        verification_perms = _permissions_for(VERIFICATION_PERMISSIONS)
        verification_group, _ = Group.objects.get_or_create(name='Vérification')
        verification_group.permissions.set(verification_perms)

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"Rôles à jour : Modérateur ({len(moderator_perms)} permissions), "
                f"Administrateur ({len(admin_perms)} permissions), "
                f"Vérification ({len(verification_perms)} permissions)."
            ))
