"""Abonnés de `notifications` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
from datetime import datetime

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
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
CAP_LEAVE = identity_services.CAP_ORG_LEAVE  # détenue par tous les rôles : sert à joindre toute l'équipe
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


REPLY_CAPABILITY = 'message.reply'  # équipe qui reçoit les messages d'une organisation (ADR 0006, D6)
REQUESTERS_CAPABILITY = 'contact.view_requesters'  # équipe qui voit « qui a demandé » (l'analyste n'y a pas droit)


def _seller_context(event):
    """(type, id) du contexte vendeur d'une charge utile de contact ou d'échange. Version 1 encore en file : le
    vendeur était un compte (`seller_id`), lu comme son contexte `USER`. Type inconnu : erreur définitive."""
    payload = event.payload
    if event.version == 1:
        return CONTEXT_USER, _user_id(_require(payload, 'seller_id')[0])
    context_type, context_id = _require(payload, 'seller_context_type', 'seller_context_id')
    if context_type not in (CONTEXT_USER, CONTEXT_PROVIDER, CONTEXT_ORGANIZATION):
        raise PermanentEventError("charge utile invalide")
    return context_type, _user_id(context_id)


def _buyer_name(user_id_value):
    """Nom de l'acheteur vu par l'équipe du vendeur : forme abrégée (« Marie K. »), jamais le nom complet."""
    user_id = _user_id(user_id_value)
    return identity_services.requester_display_name(identity_services.get_full_names([user_id]).get(user_id))


def _notify_context(event, capability, **notification):
    """Une notification par destinataire du contexte vendeur, résolu À LA LIVRAISON (équipe du moment : un membre
    révoqué entre-temps n'est pas notifié). Une organisation : la notification est rattachée à l'organisation.
    Aucune donnée de membre dans la charge utile ni dans les journaux."""
    context_type, context_id = _seller_context(event)
    for recipient_id in identity_services.get_context_recipients(context_type, context_id, capability):
        services.notify(
            user_id=recipient_id,
            context=(context_type, context_id) if context_type == CONTEXT_ORGANIZATION else None,
            **notification,
        )


@subscribe('marketplace.contact_recorded', name='notifications.notify_contact', versions=(1, 2))
def notify_contact(event):
    sender_id, title = _require(event.payload, 'sender_id', 'offer_title')
    _notify_context(
        event, REPLY_CAPABILITY, notification_type=services.CONTACT,
        title="Nouvelle demande de contact",
        content=f"{_buyer_name(sender_id)} vous a contacté pour {title}",
        link='/messages',
    )


@subscribe('marketplace.contact_revealed', name='notifications.notify_contact_revealed', versions=(1, 2))
def notify_contact_revealed(event):
    """Le vendeur apprend qu'un utilisateur a obtenu son numéro (ADR 0005, C7) : nom d'affichage
    « Marie K. » (`requester_display_name`, nettoyé comme la liste), jamais de numéro. Organisation : les membres
    qui ont `contact.view_requesters` (comme la liste « qui a demandé »)."""
    sender_id, title = _require(event.payload, 'sender_id', 'offer_title')
    sender = _user_id(sender_id)
    name = identity_services.requester_display_name(identity_services.get_full_names([sender]).get(sender))
    _notify_context(
        event, REQUESTERS_CAPABILITY, notification_type=services.CONTACT,
        title="Votre numéro a été demandé",
        content=f"{name} a demandé votre numéro pour {title}",
        link='/dashboard',
    )


@subscribe('marketplace.exchange_proposed', name='notifications.notify_exchange', versions=(1, 2))
def notify_exchange(event):
    sender_id, title = _require(event.payload, 'sender_id', 'offer_title')
    _notify_context(
        event, REPLY_CAPABILITY, notification_type=services.EXCHANGE,
        title="Nouvelle proposition d'échange",
        content=f"{_buyer_name(sender_id)} propose un échange pour {title}",
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
    if payload.get('confirmed'):
        # Entrée après confirmation d'une invitation Administrateur : la personne reçoit la seule notification
        # « Votre accès … est confirmé. » (`notify_invitation_outcome`, décision du chef de projet, L1-01-B7).
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
    # D11 : la notification d'ajout ou de changement de rôle mène à l'équipe ; celle de retrait reste personnelle.
    link = '/dashboard' if change == 'revoked' else f'/organizations/{organization}/team'
    services.notify(
        user_id=target, notification_type=services.SYSTEM, title=title, content=content, link=link, context=context,
    )


@subscribe('identity.membership_changed', name='notifications.purge_context_notifications')
def purge_context_notifications(event):
    """Révocation : supprime les notifications que ce compte avait reçues au titre de l'organisation (il ne doit
    rien en conserver ni en lire) ; rétrogradation : supprime celles dont il n'a plus la capacité ; retour : supprime les anciennes. Idempotent. Les nouvelles notifications ne l'atteignent plus (destinataires
    résolus à la livraison) et `visible_notifications` masque celles qui arriveraient après coup."""
    payload = event.payload
    organization_id, user_id, change = _require(payload, 'organization_id', 'user_id', 'change')
    organization, user = _user_id(organization_id), _user_id(user_id)
    if change == 'revoked':
        services.purge_context_notifications(user, CONTEXT_ORGANIZATION, organization)
    elif change == 'reactivated':
        # Retour d'un ancien membre : les lignes antérieures à l'événement sont périmées (la notification de retour,
        # créée après, est conservée).
        services.purge_context_notifications(user, CONTEXT_ORGANIZATION, organization, before=event.created_at)
    elif change == 'role_changed':
        # Rétrogradation : le membre ne garde pas les notifications dont il n'a plus la capacité (avis -> `review.reply`,
        # expiration -> `offer.edit`). Idempotent ; une promotion ne purge rien.
        role = payload.get('new_role')
        lost = [
            kind for kind, capability in ((services.COMMENT, CAP_REVIEW_REPLY), (services.EXPIRATION, CAP_OFFER_EDIT))
            if not identity_services.context_has_capability(CONTEXT_ORGANIZATION, role, capability)
        ]
        if lost:
            services.purge_context_notifications(user, CONTEXT_ORGANIZATION, organization, notification_types=lost)


_INVITATION_OUTCOMES = {
    'accepted': ("Invitation acceptée", "acceptée"),
    'declined': ("Invitation refusée", "refusée"),
}


@subscribe('identity.organization_invitation_changed', name='notifications.notify_invitation_outcome')
def notify_invitation_outcome(event):
    """Issue d'une invitation (ADR 0008 §6, ADR 0010 §7). Textes neutres : jamais le nom de la personne, ni son
    téléphone ou l'indice de téléphone, ni l'étiquette, ni le jeton ; destinataires résolus À LA LIVRAISON.
    - `accepted`, `declined` : l'INVITEUR SEUL, s'il est toujours destinataire de `org.manage_members` ;
    - `awaiting_confirmation` : les comptes qui peuvent confirmer (l'émetteur s'il en a toujours l'autorité, les
      administrateurs principaux effectifs) ;
    - `confirmed` : la personne entrée, et les comptes qui pouvaient confirmer (sauf l'auteur de la confirmation) ;
    - `rejected` : la personne qui avait accepté, dans son contexte personnel (elle n'est pas membre), sans le nom du
      confirmateur.
    Rien n'est notifié pour une création ou une révocation."""
    payload = event.payload
    organization_id, change = _require(payload, 'organization_id', 'change')
    organization = _user_id(organization_id)
    if change in _INVITATION_OUTCOMES:
        _notify_inviter_of_outcome(payload, organization, change)
    elif change == 'awaiting_confirmation':
        _notify_confirmers(event, organization)
    elif change == 'confirmed':
        _notify_confirmed(event, organization)
    elif change == 'rejected':
        accepted_by = payload.get('accepted_by_id')
        if accepted_by:
            services.notify(
                user_id=_user_id(accepted_by), notification_type=services.SYSTEM, title="Demande non confirmée",
                content=f"Votre demande pour rejoindre « {_organization_name(organization)} » n'a pas été confirmée.",
                link='/profiles',
            )


def _notify_inviter_of_outcome(payload, organization, change):
    inviter = payload.get('inviter_id')
    if not inviter:
        return
    inviter = _user_id(inviter)
    if inviter not in identity_services.get_organization_recipients(organization, 'org.manage_members'):
        return
    title, outcome = _INVITATION_OUTCOMES[change]
    role = identity_services.get_role_label(payload.get('role'))
    services.notify(
        user_id=inviter, notification_type=services.SYSTEM, title=title,
        content=f"Une invitation à rejoindre « {_organization_name(organization)} » avec le rôle {role} a été {outcome}.",
        link=f'/organizations/{organization}/team', context=(CONTEXT_ORGANIZATION, organization),
    )


def _confirmer_ids(event, organization):
    invitation_id = _require(event.payload, 'invitation_id')[0]
    return identity_services.get_invitation_confirmer_ids(organization, _user_id(invitation_id))


def _notify_confirmers(event, organization):
    """Une invitation Administrateur a été acceptée : l'émetteur (s'il peut encore confirmer) et tous les
    administrateurs principaux effectifs doivent confirmer l'identité de la personne avant tout accès."""
    name = _organization_name(organization)
    role = identity_services.get_role_label(event.payload.get('role'))
    for recipient in _confirmer_ids(event, organization):
        services.notify(
            user_id=recipient, notification_type=services.SYSTEM, title="Confirmation requise",
            content=(
                f"Une invitation comme {role} pour « {name} » a été acceptée. Confirmez l'identité de la "
                "personne avant de lui ouvrir l'accès."
            ),
            link=f'/organizations/{organization}/team', context=(CONTEXT_ORGANIZATION, organization),
        )


def _notify_confirmed(event, organization):
    payload = event.payload
    name = _organization_name(organization)
    link = f'/organizations/{organization}/team'
    accepted_by = payload.get('accepted_by_id')
    if accepted_by:
        services.notify(
            user_id=_user_id(accepted_by), notification_type=services.SYSTEM, title="Accès confirmé",
            content=f"Votre accès à « {name} » est confirmé.", link=link,
            context=(CONTEXT_ORGANIZATION, organization),
        )
    actor = payload.get('actor_id')
    role = identity_services.get_role_label(payload.get('role'))
    for recipient in _confirmer_ids(event, organization):
        if str(recipient) in (actor, accepted_by):
            continue
        services.notify(
            user_id=recipient, notification_type=services.SYSTEM, title="Accès confirmé",
            content=f"Une invitation comme {role} pour « {name} » a été confirmée.", link=link,
            context=(CONTEXT_ORGANIZATION, organization),
        )


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
    """Annonce la suspension, l'archivage ou la réactivation d'une organisation à toute son équipe active
    (administrateurs principaux, administrateurs, éditeurs, analystes, membres ; hors auteur de l'action). Texte neutre,
    sans motif ni auteur ; le lien mène à la page de l'organisation. Les autres contextes (compte, prestataire)
    ne produisent aucune notification ici. Aucun membre actif : rien n'est envoyé."""
    payload = event.payload
    context_type, context_id, reason = _require(payload, 'context_type', 'context_id', 'reason')
    if context_type != CONTEXT_ORGANIZATION or reason not in _STATUS_MESSAGES:
        return
    organization = _user_id(context_id)
    name = _organization_name(organization)
    title, template = _STATUS_MESSAGES[reason]
    for recipient in identity_services.get_organization_recipients(organization, CAP_LEAVE):
        if str(recipient) == payload.get('actor_id'):
            continue
        services.notify(
            user_id=recipient, notification_type=services.SYSTEM, title=title, content=template.format(name=name),
            link=f'/organizations/{organization}', context=(CONTEXT_ORGANIZATION, organization),
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
    """Annonce la décision du personnel sur une pièce de l'organisation à ses administrateurs principaux et
    administrateurs (capacité de dépôt de pièces). Ni le motif de refus ni le nom du décideur ne sont repris."""
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
