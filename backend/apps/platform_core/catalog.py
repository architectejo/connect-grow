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
    EventType('marketplace.contact_recorded'),
    # ADR 0005 : sans aucun numéro dans la charge utile. Émetteur et abonné (notifications) ajoutés par T3.
    EventType('marketplace.contact_revealed', no_subscriber=True, emitter_pending=True),
    EventType('marketplace.exchange_proposed'),
    EventType('marketplace.offer_expiring_soon'),
    # ADR 0005, C10 : émetteur (`messaging`) et abonné `marketplace` ajoutés par T4.
    EventType('messaging.contact_message_delivered', no_subscriber=True, emitter_pending=True),
    EventType('visibility.offer_viewed'),
    EventType('visibility.offer_shared'),
    EventType('visibility.ranking_settings_changed'),
    # Versions 2 (ADR 0004) : `recipient_id` désigne le destinataire de la notification ;
    # `reviews_count` est le nombre d'avis croisés.
    EventType('reviews.review_posted', version=2),
    EventType('reviews.review_replied'),
    EventType('reviews.crossed_reviews_detected', version=2),
)

EVENT_TYPES = {t.name: t for t in _TYPES}
