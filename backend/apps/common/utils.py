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


def seconds_until_next_day():
    """Secondes avant minuit (fuseau courant) : délai à annoncer (`Retry-After`) quand une limite
    quotidienne est atteinte, puisque les compteurs repartent à zéro au changement de jour."""
    import math

    from django.utils import timezone

    now = timezone.localtime()
    _, end = day_bounds(now.date())
    return max(1, math.ceil((end - now).total_seconds()))


def day_bounds(day):
    """Début (inclus) et fin (exclue) d'un jour du fuseau courant, en datetimes aware.
    À préférer à `created_at__date` : bornes explicites, portables SQLite/MySQL."""
    from datetime import datetime, time, timedelta

    from django.utils import timezone

    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end
