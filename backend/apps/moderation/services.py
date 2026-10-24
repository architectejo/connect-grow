"""Interface publique du domaine `moderation` pour les autres domaines.

Un signalement ou une entrée du journal désigne sa cible par (`target_type`, `target_id`) : la
modération ne lit jamais les modèles des autres domaines, elle interroge leur `services.py`
(`get_report_labels`, par lot) selon le registre `TARGET_RESOLVERS`.
"""
from datetime import timedelta
from importlib import import_module

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.common.utils import parse_uuid, seconds_until_next_day
from apps.notifications import services as notification_services

from .models import AuditLog, ModerationSettings, Report, Sanction

AUTHOR_RESPONSE_MAX_LENGTH = 1000

# Type de cible -> module de services du domaine propriétaire.
TARGET_RESOLVERS = {
    'offer': 'apps.marketplace.services',
    'user': 'apps.identity.services',
    'review': 'apps.reviews.services',
    'message': 'apps.messaging.services',
}


class ReportRefused(Exception):
    """Signalement refusé (message en français) ; `duplicate` distingue le doublon (409). `code`
    renseigné : refus codé (`{detail, code}`) au statut `status_code` plutôt qu'une erreur de champ."""

    def __init__(self, message, duplicate=False, code=None, status_code=400, wait=None):
        super().__init__(message)
        self.wait = wait  # secondes avant de pouvoir réessayer (en-tête Retry-After des 429)
        self.duplicate = duplicate
        self.code = code
        self.status_code = status_code


def _raw_target_author(target_type, target_id):
    module = TARGET_RESOLVERS.get(target_type)
    return import_module(module).get_report_authors([target_id]).get(target_id) if module else None


def resolve_target_authors(target_type, target_id) -> frozenset:
    """Comptes qui sont « l'auteur » de la cible : un seul pour un avis, un message ou un compte ; pour une offre,
    tous les comptes qui agissent pour son contexte vendeur (le compte, le titulaire du prestataire, les membres
    actifs de l'organisation : ADR 0006, 19.3 n°7). Le domaine propriétaire renvoie un UUID ou une collection."""
    value = _raw_target_author(target_type, target_id)
    if value is None:
        return frozenset()
    if isinstance(value, (set, frozenset, list, tuple)):
        return frozenset(value)
    return frozenset({value})


def resolve_target_author(target_type, target_id):
    """UUID de l'auteur UNIQUE de la cible (rédacteur d'un avis, expéditeur, compte lui-même), ou None s'il n'y en a
    pas ou s'il y en a plusieurs (offre d'une organisation : voir `resolve_target_authors`)."""
    authors = resolve_target_authors(target_type, target_id)
    return next(iter(authors)) if len(authors) == 1 else None


def ensure_can_report(reporter, target_type, target_id, reason=None):
    """Règles d'un nouveau signalement : pas de signalement de sa propre cible, un seul signalement
    ouvert par (auteur, cible). Garantie en couche service, sans contrainte conditionnelle.
    Le motif « contact fictif » est réservé au vendeur concerné par l'avis signalé (ADR 0004)."""
    if reason == Report.REASON_CONTACT_FICTIF:
        _ensure_can_report_fictitious_contact(reporter, target_type, target_id)
    if reporter.pk in resolve_target_authors(target_type, target_id):
        raise ReportRefused("Vous ne pouvez pas signaler votre propre contenu ou votre propre compte.")
    if Report.objects.filter(
        reporter=reporter, target_type=target_type, target_id=target_id, status__in=Report.OPEN_STATUSES,
    ).exists():
        raise ReportRefused("Vous avez déjà signalé cet élément ; le signalement est en cours de traitement.", True)


def _ensure_can_report_fictitious_contact(reporter, target_type, target_id):
    if target_type != 'review':
        raise ReportRefused(
            "Le motif « contact fictif » ne s'applique qu'à un avis.", code='invalid_reason', status_code=400,
        )
    if not import_module(TARGET_RESOLVERS['review']).is_review_seller(target_id, reporter):
        raise ReportRefused(
            "Seul le vendeur concerné peut signaler un contact fictif sur cet avis.",
            code='not_seller', status_code=403,
        )
    fictitious = Report.objects.filter(
        target_type=target_type, target_id=target_id, reason=Report.REASON_CONTACT_FICTIF,
    )
    if fictitious.filter(status__in=Report.OPEN_STATUSES).exists():
        raise ReportRefused(
            "Un signalement de contact fictif est déjà en cours de traitement pour cet avis.", True,
        )
    # Pas d'acharnement : un avis dont le contact a déjà été reconnu réel ne peut plus être signalé
    # pour ce motif, et chaque vendeur a un plafond quotidien (réglage en base).
    if fictitious.filter(status=Report.STATUS_REJETE).exists():
        raise ReportRefused(
            "Ce signalement a déjà été examiné et rejeté par la modération : il ne peut pas être redéposé.",
            code='report_already_rejected', status_code=409,
        )
    start_of_day = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    limit = get_settings().fictitious_contact_daily_limit
    today = Report.objects.filter(
        reporter=reporter, reason=Report.REASON_CONTACT_FICTIF, created_at__gte=start_of_day,
    ).count()
    if today >= limit:
        raise ReportRefused(
            f"Vous avez atteint la limite de {limit} signalements de contact fictif par jour.",
            code='report_daily_limit', status_code=429, wait=seconds_until_next_day(),
        )


def get_settings() -> ModerationSettings:
    return ModerationSettings.get_solo()


# Types de cible produits par les signalements automatiques (avis croisés, CDC 3.7) ; chacun
# doit avoir un résolveur dans TARGET_RESOLVERS (test), sinon le signalement serait illisible.
AUTOMATIC_TARGET_TYPES = frozenset({'review', 'user'})


def record_audit(actor, action, target=None, details='', context=None):
    """Journalise une action sensible (règle 12) dans l'AuditLog. Synchrone, sans outbox :
    une action sensible ne doit jamais exister sans sa trace (ADR 0002, notes R1).
    `context` : `(type, id)` ou `ActingContext` du contexte sous lequel l'action s'exécute (ADR 0006, A10)."""
    return AuditLog.record(actor, action, target=target, details=details, context=context)


def count_audit_days(actor_id, action, since) -> int:
    """Nombre de JOURS distincts (fuseau local) où l'acteur a une entrée de ce type depuis `since` :
    une rafale le même jour ne compte qu'une fois (détection d'abus répétés sans faux positif)."""
    stamps = AuditLog.objects.filter(actor_id=actor_id, action=action, created_at__gte=since).values_list(
        'created_at', flat=True,
    )
    return len({timezone.localtime(stamp).date() for stamp in stamps})


def has_audit_since(actor_id, action, target_id, since) -> bool:
    """Vrai si l'acteur a déjà une entrée de ce type sur cette cible depuis `since` (dédoublonnage de trace)."""
    return AuditLog.objects.filter(
        actor_id=actor_id, action=action, target_id=target_id, created_at__gte=since,
    ).exists()


def is_user_restricted(user_id) -> bool:
    """Vrai si le compte fait l'objet d'une sanction active qui bloque le compte (suspension ou
    bannissement non échus) : il ne peut alors ni contacter un vendeur ni obtenir un numéro.
    Un avertissement ou le masquage d'une annonce ne restreint pas le contact."""
    now = timezone.now()
    return Sanction.objects.filter(
        user_id=user_id, is_active=True, sanction_type__in=Sanction.ACCOUNT_BLOCKING_TYPES,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now)).exists()


def get_restricted_user_ids(user_ids) -> set:
    """Parmi `user_ids`, les comptes sous sanction bloquante en cours (une requête) : variante par lot de
    `is_user_restricted`, pour recalculer la visibilité publique de vendeurs (ADR 0006, A7)."""
    wanted = list(user_ids)
    if not wanted:
        return set()
    now = timezone.now()
    return set(
        Sanction.objects.filter(
            user_id__in=wanted, is_active=True, sanction_type__in=Sanction.ACCOUNT_BLOCKING_TYPES,
        ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now)).values_list('user_id', flat=True)
    )


def record_settings_change(actor, obj, old_values: dict, new_values: dict):
    """Journalise la modification d'un réglage du back-office (règle 12) avec l'ancienne et la
    nouvelle valeur de chaque champ modifié."""
    changes = '; '.join(f"{name} : {old_values.get(name)!r} -> {new_values[name]!r}" for name in new_values)
    return AuditLog.record(actor, 'SETTINGS_CHANGED', target=obj, details=f"{obj._meta.model_name} : {changes}")


REASON_CONTACT_FICTIF = Report.REASON_CONTACT_FICTIF
REASON_SPAM = Report.REASON_SPAM


def has_resolved_report(target_type, target_id, reason) -> bool:
    """Vrai si un signalement de ce motif sur cette cible a été validé (traité) par la modération."""
    return Report.objects.filter(
        target_type=target_type, target_id=target_id, reason=reason, status=Report.STATUS_TRAITE,
    ).exists()


def record_report_filed(report) -> None:
    """Journalise le dépôt d'un signalement « contact fictif » (règle 12) et en informe l'auteur de
    l'avis, sans révéler plus que « le vendeur ». Il n'est pas visible publiquement ; il entre dans
    la file de modération (statut « en attente »)."""
    if report.reason == Report.REASON_CONTACT_FICTIF:
        AuditLog.record(report.reporter, 'CONTACT_FICTIF_REPORTED', target=report, details=report.description[:200])
        _notify_review_author(
            report, "Votre avis est contesté",
            "Le vendeur conteste le contact à l'origine de votre avis. Vous pouvez le modifier et "
            "répondre à la modération avant sa décision ; vous ne pouvez pas le supprimer d'ici là.",
        )


def apply_decision(report, actor) -> None:
    """Conséquences de la décision de la modération sur un signalement « contact fictif » (autres
    motifs : aucun effet automatique). Retenu (traité) : l'avis est masqué (le module des avis
    recalcule ses moyennes) ; rejeté : l'avis reste et le rejet est journalisé avec l'avis visé. Dans
    les deux cas l'auteur est informé, avec un motif court et sans identité du signaleur."""
    if report.reason != Report.REASON_CONTACT_FICTIF or report.target_type != 'review':
        return
    if report.status == Report.STATUS_TRAITE:
        import_module(TARGET_RESOLVERS['review']).reject_fictitious_contact(report.target_id, actor)
        _notify_review_author(
            report, "Votre avis a été masqué",
            "La modération a retenu le signalement du vendeur : le contact n'a pas pu être établi. "
            "Votre avis est masqué et ne compte plus dans les notes.",
        )
    elif report.status == Report.STATUS_REJETE:
        AuditLog.objects.create(
            actor=actor, action='CONTACT_FICTIF_REJECTED', target_type=report.target_type,
            target_id=report.target_id, details=f"Signalement {report.pk} rejeté",
        )
        _notify_review_author(
            report, "Votre avis est maintenu",
            "La modération n'a pas retenu le signalement du vendeur : votre avis reste publié.",
        )


# Motif des signalements automatiques d'avis croisés (CDC 3.7), exposé sans importer le modèle.
REASON_CROSSED_REVIEWS = Report.REASON_AVIS_CROISES


def resolve_target_labels(target_type, target_ids) -> dict:
    """Libellés des cibles d'un même type, indexés par UUID ; une cible introuvable est absente.
    Un type inconnu renvoie un dictionnaire vide."""
    module = TARGET_RESOLVERS.get(target_type)
    if module is None:
        return {}
    return import_module(module).get_report_labels(target_ids)


def resolve_target(target_type, target_id):
    """(UUID canonique, libellé) de la cible, ou None si le type est inconnu, l'identifiant mal
    formé ou la cible inexistante. La forme canonique regroupe les écritures d'un même UUID."""
    parsed = parse_uuid(target_id)
    if parsed is None:
        return None
    label = resolve_target_labels(target_type, [parsed]).get(parsed)
    return None if label is None else (parsed, label)


def resolve_labels_for_reports(reports) -> dict:
    """Libellés de la cible de chaque signalement, `{(target_type, target_id): libellé}`,
    en une requête par type de cible."""
    ids_by_type = {}
    for report in reports:
        ids_by_type.setdefault(report.target_type, set()).add(report.target_id)
    labels = {}
    for target_type, ids in ids_by_type.items():
        for target_id, label in resolve_target_labels(target_type, ids).items():
            labels[(target_type, target_id)] = label
    return labels


def file_automatic_report(target_type, target_id, reason, description='', only_open=False):
    """Dépose dans la file de modération un signalement émis par le système (sans auteur), pour
    une cible désignée par (`target_type`, `target_id`) : aucune instance d'un autre domaine.
    Un seul signalement par cible et par motif : renvoie None s'il existe déjà (idempotent).
    `only_open` : ne dédoublonne que contre les signalements OUVERTS ; un signalement clos
    n'empêche pas d'en rouvrir un si l'abus recommence."""
    if target_type not in AUTOMATIC_TARGET_TYPES:
        raise ValueError(f"Type de cible non pris en charge pour un signalement automatique : {target_type}")
    existing = Report.objects.filter(target_type=target_type, target_id=target_id, reason=reason)
    if only_open:
        existing = existing.filter(status__in=Report.OPEN_STATUSES)
    if existing.exists():
        return None
    return Report.objects.create(
        target_type=target_type, target_id=target_id, reporter=None, reason=reason, description=description,
    )


def has_open_report(target, grave_only=False) -> bool:
    """Vrai si la cible fait l'objet d'un signalement non clos (en attente ou pris en charge) ;
    `grave_only` ne retient que les motifs de fond (`Report.GRAVE_REASONS`)."""
    reports = Report.objects.filter(
        target_type=target._meta.model_name, target_id=target.pk, status__in=Report.OPEN_STATUSES,
    )
    if grave_only:
        reports = reports.filter(reason__in=Report.GRAVE_REASONS)
    return reports.exists()


def get_open_report_states(target_type, target_ids) -> dict:
    """État des signalements ouverts par cible, en une requête : `{cible: {'grave', 'contest_report_id',
    'contest_responded'}}` ; une cible sans signalement ouvert est absente. Réservé à l'auteur de la
    cible : ne renvoie ni le signaleur ni la description (règle 10)."""
    states = {}
    rows = Report.objects.filter(
        target_type=target_type, target_id__in=list(target_ids), status__in=Report.OPEN_STATUSES,
    ).values_list('target_id', 'id', 'reason', 'author_responded_at')
    for target_id, report_id, reason, responded_at in rows:
        state = states.setdefault(
            target_id, {'grave': False, 'contest_report_id': None, 'contest_responded': False},
        )
        if reason in Report.GRAVE_REASONS:
            state['grave'] = True
        if reason == Report.REASON_CONTACT_FICTIF:
            state['contest_report_id'] = report_id
            state['contest_responded'] = responded_at is not None
    return states


def count_overdue_fictitious_reports() -> int:
    """Signalements « contact fictif » encore ouverts au-delà du délai cible de traitement."""
    limit = timezone.now() - timedelta(hours=get_settings().report_processing_target_hours)
    return Report.objects.filter(
        reason=Report.REASON_CONTACT_FICTIF, status__in=Report.OPEN_STATUSES, created_at__lt=limit,
    ).count()


def _notify_review_author(report, title, content):
    author_id = resolve_target_author(report.target_type, report.target_id)
    if author_id is not None:
        # Lien vers l'annonce de l'avis (domaine des avis) ; vide si l'annonce n'existe plus.
        link = import_module(TARGET_RESOLVERS[report.target_type]).get_report_links([report.target_id]).get(
            report.target_id, '',
        )
        notification_services.notify(
            user_id=author_id, notification_type=notification_services.SYSTEM, title=title, content=content,
            link=link,
        )


class AuthorResponseRefused(Exception):
    """Réponse de l'auteur refusée : `code` stable et statut HTTP suggéré."""

    def __init__(self, message, code, status_code=409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def submit_author_response(report, user, text):
    """Recours de l'auteur d'un avis signalé « contact fictif » : une seule réponse, tant que le
    signalement est ouvert ; journalisé. Le contrôle « l'appelant est l'auteur » est fait par la vue
    (`resolve_target_author`), qui répond 404 sinon."""
    text = (text or '').strip()
    if not text or len(text) > AUTHOR_RESPONSE_MAX_LENGTH:
        raise AuthorResponseRefused(
            f"La réponse doit contenir de 1 à {AUTHOR_RESPONSE_MAX_LENGTH} caractères.", 'invalid_response', 400,
        )
    with transaction.atomic():
        # Mise à jour conditionnelle : une seule réponse, même en cas de requêtes simultanées.
        done = Report.objects.filter(
            pk=report.pk, status__in=Report.OPEN_STATUSES, author_responded_at__isnull=True,
        ).update(author_response=text, author_responded_at=timezone.now(), updated_at=timezone.now())
        if not done:
            report.refresh_from_db()
            if report.status not in Report.OPEN_STATUSES:
                raise AuthorResponseRefused("Ce signalement est déjà clos.", 'report_closed')
            raise AuthorResponseRefused("Vous avez déjà répondu à ce signalement.", 'already_responded')
        report.refresh_from_db()
        AuditLog.record(user, 'REPORT_AUTHOR_RESPONDED', target=report, details=text[:200])
    return report
