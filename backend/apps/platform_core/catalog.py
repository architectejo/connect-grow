"""Catalogue des types d'événements de domaine : documentation exécutable (ADR 0003, §2.4).

Chaque type est `<domaine>.<fait_au_passé>`, publié par un seul domaine (le préfixe). Un type
publié ou écouté doit figurer ici : le contrôle Django `platform_core.E001` l'exige.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class EventType:
    name: str
    version: int = 1
    # Vrai si l'événement n'a volontairement aucun abonné (simple trace).
    no_subscriber: bool = False
    # Vrai si le type est déclaré avant son émetteur (livraison en plusieurs tâches, ADR 0005) ;
    # à retirer dès que le service qui le publie existe.
    emitter_pending: bool = False

    @property
    def domain(self):
        return self.name.split('.', 1)[0]


_TYPES = (
    # ADR 0006, section 8. Charges utiles : UUID et valeurs simples, aucune donnée personnelle.
    # Abonnés : `notifications.notify_membership_change` (prévient la personne concernée) et
    # `notifications.purge_context_notifications` (révocation : supprime ses notifications de l'organisation).
    EventType('identity.membership_changed'),
    # Abonnés : `marketplace.sync_seller_visibility` (T5a) ; `notifications.notify_organization_status` (T6).
    EventType('identity.seller_context_status_changed'),
    # Identité d'une organisation modifiée (T8) : noms de champs seulement, aucune valeur.
    EventType('identity.organization_updated', no_subscriber=True),
    # Émetteur : `decide_kyc_document` (T4) ; abonné `notifications.notify_kyb_decision` (T6).
    EventType('identity.organization_verification_changed'),
    # Version 2 (ADR 0006, section 8) : `seller_id` (compte) remplacé par `seller_context_type`/`seller_context_id` ;
    # les destinataires sont résolus à la livraison par `identity`.
    EventType('marketplace.contact_recorded', version=2),
    # ADR 0005 : sans aucun numéro dans la charge utile ; abonné : notifications (prévient le vendeur).
    EventType('marketplace.contact_revealed', version=2),
    EventType('marketplace.exchange_proposed', version=2),
    # Version 2 (ADR 0006, section 8) : `seller_context_type/id` à la place de `seller_id` ; un événement par offre,
    # destinataires (capacité `offer.edit`) résolus par l'abonné à la livraison.
    EventType('marketplace.offer_expiring_soon', version=2),
    # ADR 0005, C10 : abonné `marketplace` (pose `delivered_at`) ; ni texte ni numéro dans la charge utile.
    EventType('messaging.contact_message_delivered'),
    EventType('visibility.offer_viewed'),
    EventType('visibility.offer_shared'),
    EventType('visibility.ranking_settings_changed'),
    # `review_posted` v3 (ADR 0006, section 8) : plus de `recipient_id`, l'abonné résout les destinataires à la
    # livraison d'après le contexte vendeur (`seller_context_type/id`). `crossed_reviews_detected` v2 (ADR 0004) :
    # `reviews_count` est le nombre d'avis croisés.
    EventType('reviews.review_posted', version=3),
    EventType('reviews.review_replied'),
    EventType('reviews.crossed_reviews_detected', version=2),
)

EVENT_TYPES = {t.name: t for t in _TYPES}
