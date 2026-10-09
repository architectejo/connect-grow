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
