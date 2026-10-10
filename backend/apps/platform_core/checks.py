"""Contrôles Django du catalogue d'événements (ADR 0003, §2.4)."""
from django.core.checks import Error, register

from . import registry
from .catalog import EVENT_TYPES


@register()
def check_event_catalog(app_configs, **kwargs):
    errors = []
    for subscriber in registry.all_subscribers():
        if subscriber.event_type not in EVENT_TYPES:
            errors.append(Error(
                f"L'abonné « {subscriber.name} » écoute un type absent du catalogue : {subscriber.event_type}.",
                hint="Déclarer le type dans apps/platform_core/catalog.py.", id='platform_core.E001',
            ))
    for name, spec in EVENT_TYPES.items():
        if not spec.no_subscriber and not registry.subscribers_for(name):
            errors.append(Error(
                f"Le type d'événement {name} n'a aucun abonné.",
                hint="Ajouter un abonné dans events.py ou déclarer no_subscriber=True.", id='platform_core.E002',
            ))
    return errors
