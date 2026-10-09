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

    @property
    def domain(self):
        return self.name.split('.', 1)[0]


_TYPES = (
    EventType('marketplace.contact_recorded'),
    EventType('marketplace.exchange_proposed'),
)

EVENT_TYPES = {t.name: t for t in _TYPES}
