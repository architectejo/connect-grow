"""Registre des abonnés aux événements de domaine (ADR 0003, §2.4).

Chaque domaine déclare ses abonnés dans `apps/<domaine>/events.py`, importé par son
`AppConfig.ready()`. Un abonné reçoit un `EventData` immuable, jamais le modèle, et n'appelle
que des `services.py`. Son `name` est persisté dans `OutboxDelivery.handler` : ne jamais le
renommer sans migration de données.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime


class PermanentEventError(Exception):
    """Échec définitif d'un abonné (version inconnue, charge utile invalide) : la livraison
    passe directement en `dead`, sans nouvelle tentative."""


@dataclass(frozen=True)
class EventData:
    id: uuid.UUID
    event_type: str
    version: int
    payload: dict
    created_at: datetime


@dataclass(frozen=True)
class Subscriber:
    event_type: str
    name: str
    func: callable
    versions: tuple


_BY_NAME = {}
_BY_TYPE = {}


def subscribe(event_type, *, name, versions=(1,)):
    """Décorateur : enregistre `func` comme abonné `name` de `event_type`. Un doublon de nom
    interrompt le démarrage."""
    def decorator(func):
        if name in _BY_NAME and _BY_NAME[name].func is not func:
            raise RuntimeError(f"Abonné déjà enregistré sous le nom « {name} ».")
        subscriber = Subscriber(event_type=event_type, name=name, func=func, versions=tuple(versions))
        _BY_NAME[name] = subscriber
        bucket = _BY_TYPE.setdefault(event_type, {})
        bucket[name] = subscriber
        return func
    return decorator


def subscribers_for(event_type):
    """Abonnés d'un type d'événement, triés par nom (ordre stable)."""
    return [s for _, s in sorted(_BY_TYPE.get(event_type, {}).items())]


def get_subscriber(name):
    return _BY_NAME.get(name)


def all_subscribers():
    return list(_BY_NAME.values())


def unregister(name):
    """Retire un abonné (réservé aux tests)."""
    subscriber = _BY_NAME.pop(name, None)
    if subscriber is not None:
        _BY_TYPE.get(subscriber.event_type, {}).pop(name, None)
