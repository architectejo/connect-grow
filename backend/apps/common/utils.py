import uuid
from typing import Optional


def parse_uuid(value) -> Optional[uuid.UUID]:
    """Convertit une valeur en UUID ; renvoie None si elle n'est pas valide."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def day_bounds(day):
    """Début (inclus) et fin (exclue) d'un jour du fuseau courant, en datetimes aware.
    À préférer à `created_at__date` : bornes explicites, portables SQLite/MySQL."""
    from datetime import datetime, time, timedelta

    from django.utils import timezone

    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end
