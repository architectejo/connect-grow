"""Abonnés de `notifications` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
from datetime import datetime

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_USER
from apps.common.utils import parse_uuid
from apps.identity import services as identity_services
from apps.platform_core.registry import PermanentEventError, subscribe
from apps.reviews import services as reviews_services

from . import services

UNKNOWN_USER = "Un utilisateur"
UNKNOWN_SELLER = "Le vendeur"
UNKNOWN_ORGANIZATION = "votre organisation"

# Capacités d'`identity` (matrice ADR 0006, section 5), désignées par leur nom stable.
CAP_REVIEW_REPLY = 'review.reply'
CAP_OFFER_EDIT = 'offer.edit'
CAP_MANAGE_MEMBERS = 'org.manage_members'
CAP_VERIFICATION_SUBMIT = 'org.verification_submit'


def _require(payload, *keys):
    """Valeurs obligatoires de la charge utile ; une clé absente ou un UUID mal formé est une
    erreur définitive (rejouer ne changera rien)."""
    try:
        return [payload[key] for key in keys]
    except (KeyError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc


def _user_id(value):
    parsed = parse_uuid(value)
    if parsed is None:
        raise PermanentEventError("charge utile invalide")
    return parsed


def _name(user_id_value):
    user_id = _user_id(user_id_value)
    return identity_services.get_full_names([user_id]).get(user_id) or UNKNOWN_USER


@subscribe('marketplace.contact_recorded', name='notifications.notify_contact')
def notify_contact(event):
    seller_id, sender_id, title = _require(event.payload, 'seller_id', 'sender_id', 'offer_title')
    services.notify(
        user_id=_user_id(seller_id), notification_type=services.CONTACT,
        title="Nouvelle demande de contact",
        content=f"{_name(sender_id)} vous a contacté pour {title}",
        link='/messages',
    )


@subscribe('marketplace.contact_revealed', name='notifications.notify_contact_revealed')
def notify_contact_revealed(event):
    """Le vendeur apprend qu'un utilisateur a obtenu son numéro (ADR 0005, C7) : nom d'affichage
    « Marie K. » (`requester_display_name`, nettoyé comme la liste), jamais de numéro."""
    seller_id, sender_id, title = _require(event.payload, 'seller_id', 'sender_id', 'offer_title')
    sender = _user_id(sender_id)
    name = identity_services.requester_display_name(identity_services.get_full_names([sender]).get(sender))
    services.notify(
        user_id=_user_id(seller_id), notification_type=services.CONTACT,
        title="Votre numéro a été demandé",
        content=f"{name} a demandé votre numéro pour {title}",
        link='/dashboard',
    )


@subscribe('marketplace.exchange_proposed', name='notifications.notify_exchange')
def notify_exchange(event):
    seller_id, sender_id, title = _require(event.payload, 'seller_id', 'sender_id', 'offer_title')
    services.notify(
        user_id=_user_id(seller_id), notification_type=services.EXCHANGE,
        title="Nouvelle proposition d'échange",
        content=f"{_name(sender_id)} propose un échange pour {title}",
        link='/messages',
    )


def _post_link(payload):
    return f"/post/{payload['offer_id']}" if payload.get('offer_id') else ''


@subscribe('reviews.review_posted', name='notifications.notify_review_posted', versions=(3,))
def notify_review_posted(event):
    """Version 3 (ADR 0006, section 8) : la charge utile désigne le contexte vendeur de l'avis ; les destinataires
    sont résolus ICI, à la livraison (état de l'équipe au moment où l'on notifie, pas à celui de la publication) :
    le compte (`USER`), le titulaire du profil (`PROVIDER`) ou les membres actifs de l'organisation dont le rôle a
    la capacité `review.reply`. Organisation sans membre éligible : aucune notification, événement traité sans
    erreur (rien à rejouer). Les versions 1 et 2 sont refusées par le registre."""
    payload = event.payload
    review_id, author_id, title, context_type, context_id = _require(
        payload, 'review_id', 'author_id', 'offer_title', 'seller_context_type', 'seller_context_id',
    )
    excerpt = reviews_services.get_review_excerpt(_user_id(review_id))
    if excerpt is None:  # avis supprimé avant la diffusion : plus rien à annoncer
        return
    context_id = _user_id(context_id)
    author = _user_id(author_id)
    author_name = identity_services.public_display_name(identity_services.get_full_names([author]).get(author))
    for recipient in identity_services.get_context_recipients(context_type, context_id, CAP_REVIEW_REPLY):
        services.notify(
            user_id=recipient, notification_type=services.COMMENT,
            title=f"Nouvel avis sur {title}",
            content=f"{author_name} a laissé un avis : {excerpt}...",
            link=_post_link(payload), context=(context_type, context_id),
        )


def _seller_display_name(context_type, context_id):
    """Nom public du côté vendeur, jamais celui du membre qui agit : organisation ou prestataire par leur nom,
    compte personnel par son nom d'affichage (« Marie K. »). Repli : « Le vendeur »."""
    parsed = parse_uuid(context_id)
    if parsed is None:
        return UNKNOWN_SELLER
    if context_type == CONTEXT_USER:
        full_name = identity_services.get_full_names([parsed]).get(parsed)
        return identity_services.public_display_name(full_name) if full_name else UNKNOWN_SELLER
    return identity_services.get_context_names([(context_type, parsed)]).get((context_type, parsed)) or UNKNOWN_SELLER


@subscribe('reviews.review_replied', name='notifications.notify_review_reply')
def notify_review_reply(event):
    """L'auteur de l'avis apprend la réponse du vendeur, nommé par son contexte (organisation, prestataire,
    personne) : le nom du membre qui a écrit la réponse n'est jamais communiqué (ADR 0006, 9.8)."""
    payload = event.payload
    author_id, title = _require(payload, 'review_author_id', 'offer_title')
    seller = _seller_display_name(payload.get('seller_context_type'), payload.get('seller_context_id'))
    services.notify(
        user_id=_user_id(author_id), notification_type=services.SYSTEM,
        title="Réponse à votre avis",
        content=f"{seller} a répondu à votre avis sur {title}",
        link=_post_link(payload),
    )


@subscribe('marketplace.offer_expiring_soon', name='notifications.notify_offer_expiration', versions=(2,))
def notify_offer_expiration(event):
    """Version 2 (ADR 0006, section 8) : un événement par offre, portant le contexte vendeur ; les destinataires
    (capacité `offer.edit`) sont résolus à la livraison. Chaque destinataire reçoit une notification rattachée au
    contexte de l'offre. Aucun destinataire éligible : rien n'est envoyé, l'événement est traité sans erreur."""
    payload = event.payload
    context_type, context_id, title, offer_id, raw_date = _require(
        payload, 'seller_context_type', 'seller_context_id', 'offer_title', 'offer_id', 'expires_at',
    )
    try:
        expires_at = datetime.fromisoformat(raw_date)
    except (ValueError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc
    context_id = _user_id(context_id)
    for recipient in identity_services.get_context_recipients(context_type, context_id, CAP_OFFER_EDIT):
        services.notify(
            user_id=recipient, notification_type=services.EXPIRATION,
            title="Votre annonce expire bientôt",
            content=f"« {title} » expire le {expires_at:%d/%m/%Y}. Renouvelez-la pour rester visible.",
            link=f"/post/{offer_id}", context=(context_type, context_id),
        )


# --- Équipe, statut du vendeur, vérification (ADR 0006, section 8) : sans aucune donnée personnelle ------------
# Les charges utiles ne portent que des identifiants et des codes ; les noms (organisation) et libellés (rôle,
# type de pièce) sont relus à la livraison. Un membre n'est jamais nommé dans une notification.

def _organization_name(organization_id):
    key = (CONTEXT_ORGANIZATION, organization_id)
    return identity_services.get_context_names([key]).get(key) or UNKNOWN_ORGANIZATION


@subscribe('identity.membership_changed', name='notifications.notify_membership_change')
def notify_membership_change(event):
    """Prévient la personne concernée d'un ajout, d'un changement de rôle, d'un retour ou d'un retrait. Personne
    n'est notifié de sa propre action (création, départ volontaire). La notification de retrait est PERSONNELLE
    (contexte nul) : l'ex-membre ne doit plus rien lire du contexte de l'organisation, mais peut savoir qu'il en
    est sorti."""
    payload = event.payload
    organization_id, user_id, change = _require(payload, 'organization_id', 'user_id', 'change')
    organization = _user_id(organization_id)
    target = _user_id(user_id)
    if payload.get('actor_id') == user_id:
        return
    name = _organization_name(organization)
    role = identity_services.get_role_label(payload.get('new_role'))
    context = (CONTEXT_ORGANIZATION, organization)
    if change in ('added', 'reactivated'):
        title, content = "Vous avez rejoint une organisation", f"Vous faites partie de « {name} » avec le rôle {role}."
    elif change == 'role_changed':
        title, content = "Votre rôle a changé", f"Votre rôle dans « {name} » est maintenant : {role}."
    elif change == 'revoked':
        title, content = "Vous ne faites plus partie d'une organisation", f"Vous ne faites plus partie de « {name} »."
        context = None
    else:
        return
    services.notify(
        user_id=target, notification_type=services.SYSTEM, title=title, content=content, link='/dashboard',
        context=context,
    )


@subscribe('identity.membership_changed', name='notifications.purge_context_notifications')
def purge_context_notifications(event):
    """Révocation : supprime les notifications que ce compte avait reçues au titre de l'organisation (il ne doit
    rien en conserver ni en lire). Idempotent. Les nouvelles notifications ne l'atteignent plus (destinataires
    résolus à la livraison) et `visible_notifications` masque celles qui arriveraient après coup."""
    organization_id, user_id, change = _require(event.payload, 'organization_id', 'user_id', 'change')
    if change != 'revoked':
        return
    services.purge_context_notifications(_user_id(user_id), CONTEXT_ORGANIZATION, _user_id(organization_id))


_STATUS_MESSAGES = {
    'suspended': (
        "Organisation suspendue", "L'organisation « {name} » a été suspendue : ses offres ne sont plus publiques.",
    ),
    'reactivated': ("Organisation réactivée", "L'organisation « {name} » a été réactivée."),
    'archived': (
        "Organisation archivée", "L'organisation « {name} » a été archivée : ses offres ne sont plus publiques.",
    ),
}


@subscribe('identity.seller_context_status_changed', name='notifications.notify_organization_status')
def notify_organization_status(event):
    """Annonce la suspension, l'archivage ou la réactivation d'une organisation à ses propriétaires et
    administrateurs (hors auteur de l'action). Les autres contextes (compte, prestataire) ne produisent aucune
    notification ici. Aucun propriétaire ou administrateur actif : rien n'est envoyé."""
    payload = event.payload
    context_type, context_id, reason = _require(payload, 'context_type', 'context_id', 'reason')
    if context_type != CONTEXT_ORGANIZATION or reason not in _STATUS_MESSAGES:
        return
    organization = _user_id(context_id)
    name = _organization_name(organization)
    title, template = _STATUS_MESSAGES[reason]
    for recipient in identity_services.get_organization_recipients(organization, CAP_MANAGE_MEMBERS):
        if str(recipient) == payload.get('actor_id'):
            continue
        services.notify(
            user_id=recipient, notification_type=services.SYSTEM, title=title, content=template.format(name=name),
            link='/dashboard', context=(CONTEXT_ORGANIZATION, organization),
        )


_KYB_MESSAGES = {
    'VALIDE': ("Pièce de vérification validée", "La pièce « {label} » de « {name} » a été validée."),
    'REFUSE': (
        "Pièce de vérification refusée",
        "La pièce « {label} » de « {name} » a été refusée. Le motif est consultable dans l'espace de vérification.",
    ),
    'REVOKED': (
        "Validation d'une pièce révoquée",
        "La validation de la pièce « {label} » de « {name} » a été révoquée. "
        "Le motif est consultable dans l'espace de vérification.",
    ),
}


@subscribe('identity.organization_verification_changed', name='notifications.notify_kyb_decision')
def notify_kyb_decision(event):
    """Annonce la décision du personnel sur une pièce de l'organisation à ses propriétaires et administrateurs
    (capacité de dépôt de pièces). Ni le motif de refus ni le nom du décideur ne sont repris."""
    organization_id, document_type, decision = _require(
        event.payload, 'organization_id', 'document_type', 'decision',
    )
    if decision not in _KYB_MESSAGES:
        return
    organization = _user_id(organization_id)
    title, template = _KYB_MESSAGES[decision]
    content = template.format(
        label=identity_services.get_document_type_label(document_type), name=_organization_name(organization),
    )
    for recipient in identity_services.get_organization_recipients(organization, CAP_VERIFICATION_SUBMIT):
        services.notify(
            user_id=recipient, notification_type=services.SYSTEM, title=title, content=content, link='/dashboard',
            context=(CONTEXT_ORGANIZATION, organization),
        )
