"""Publication et diffusion des événements de domaine (ADR 0003).

Interface publique : `publish_event` (émetteurs, dans leur transaction) et les fonctions de
diffusion appelées par les commandes `dispatch_outbox` / `purge_outbox` et par le déclencheur
`on_commit`. Aucun autre domaine n'importe les modèles de ce module.
"""
import json
import logging
import os
import time
import uuid
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import OperationalError, connection, transaction
from django.db.models import F, Min, Q
from django.utils import timezone

from . import registry
from .catalog import EVENT_TYPES
from .models import OutboxDelivery, OutboxEvent
from .registry import EventData, PermanentEventError

logger = logging.getLogger(__name__)

LAST_ERROR_MAX_LENGTH = 2000
PURGE_BATCH_SIZE = 500


class OutboxError(Exception):
    """Mauvaise utilisation de l'outbox (publication hors transaction, charge invalide…)."""


# --- Réglages (settings.py) ------------------------------------------------------

def _max_attempts():
    return settings.OUTBOX_MAX_ATTEMPTS


def _lock_timeout():
    return timedelta(seconds=settings.OUTBOX_LOCK_TIMEOUT_SECONDS)


def _backoff(attempts):
    """Délai avant la nouvelle tentative : base x 2^(tentatives-1), plafonné."""
    seconds = settings.OUTBOX_BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0))
    return timedelta(seconds=min(seconds, settings.OUTBOX_BACKOFF_MAX_SECONDS))


# --- Publication -------------------------------------------------------------------

def publish_event(event_type, *, aggregate_type, aggregate_id, payload, version=None, require_atomic=True):
    """Écrit l'événement et une livraison par abonné, dans la transaction de l'émetteur.

    Lève OutboxError hors `transaction.atomic()` (l'événement doit être validé ou annulé avec
    le changement qui l'a produit), pour un type absent du catalogue, une version qui n'est pas
    celle du catalogue, ou une charge utile non sérialisable ou trop grosse. N'appelle aucun
    abonné. `require_atomic=False` est réservé aux tests unitaires de ce module."""
    spec = EVENT_TYPES.get(event_type)
    if spec is None:
        raise OutboxError(f"Type d'événement inconnu : {event_type}.")
    version = spec.version if version is None else version
    if version != spec.version:
        raise OutboxError(f"Version {version} inconnue pour {event_type} (courante : {spec.version}).")
    if require_atomic and not connection.in_atomic_block:
        raise OutboxError("publish_event doit être appelée dans un bloc transaction.atomic().")
    try:
        encoded = json.dumps(payload)
    except (TypeError, ValueError) as exc:
        raise OutboxError(f"Charge utile non sérialisable en JSON pour {event_type}.") from exc
    if len(encoded.encode('utf-8')) > settings.OUTBOX_MAX_PAYLOAD_BYTES:
        raise OutboxError(f"Charge utile trop volumineuse pour {event_type}.")

    now = timezone.now()
    subscribers = registry.subscribers_for(event_type)
    event = OutboxEvent.objects.create(
        event_type=event_type, version=version, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
        payload=json.loads(encoded),
        status=OutboxEvent.PENDING if subscribers else OutboxEvent.DONE,
        completed_at=None if subscribers else now,
    )
    if subscribers:
        OutboxDelivery.objects.bulk_create([
            OutboxDelivery(event=event, handler=s.name, next_attempt_at=now) for s in subscribers
        ])
        if settings.OUTBOX_INLINE_DISPATCH:
            transaction.on_commit(lambda: dispatch_for_event(event.pk))
    return event.pk


# --- Diffusion ---------------------------------------------------------------------

def _due_filter(now):
    return (
        Q(status=OutboxDelivery.PENDING, next_attempt_at__lte=now)
        | Q(status=OutboxDelivery.PROCESSING, locked_at__lt=now - _lock_timeout())
    )


def _claim(pk, seen_status, seen_locked_by, now) -> Optional[str]:
    """Prise en charge par UPDATE conditionnel (portable, sans verrou de ligne) : une seule
    exécution gagne ; renvoie son jeton, ou None si une autre a gagné."""
    token = uuid.uuid4().hex
    try:
        claimed = OutboxDelivery.objects.filter(
            _due_filter(now), pk=pk, status=seen_status, locked_by=seen_locked_by,
        ).update(
            status=OutboxDelivery.PROCESSING, locked_at=now, locked_by=token, attempts=F('attempts') + 1,
        )
    except OperationalError:  # base verrouillée par un autre écrivain : l'exécution suivante reprendra
        logger.warning("Outbox : prise en charge différée (base occupée).")
        return None
    return token if claimed else None


def _describe(exc) -> str:
    """Texte stocké dans `last_error` : jamais le message d'une exception inconnue (il peut
    citer des données personnelles), seulement sa classe et son origine."""
    if isinstance(exc, (PermanentEventError, OutboxError)):
        return f"{type(exc).__name__}: {exc}"[:LAST_ERROR_MAX_LENGTH]
    tb = exc.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    origin = ''
    if tb is not None:
        origin = f" ({os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno})"
    return f"{type(exc).__name__}{origin}"[:LAST_ERROR_MAX_LENGTH]


def _refresh_event_status(event_id) -> None:
    """`done` quand toutes les livraisons sont traitées ; `dead` si l'une est en échec définitif
    et qu'aucune n'est en attente ; sinon `pending`."""
    statuses = set(OutboxDelivery.objects.filter(event_id=event_id).values_list('status', flat=True))
    now = timezone.now()
    if statuses <= {OutboxDelivery.DONE}:
        OutboxEvent.objects.filter(pk=event_id).exclude(status=OutboxEvent.DONE).update(
            status=OutboxEvent.DONE, completed_at=now,
        )
    elif OutboxDelivery.DEAD in statuses and not statuses & {OutboxDelivery.PENDING, OutboxDelivery.PROCESSING}:
        OutboxEvent.objects.filter(pk=event_id).exclude(status=OutboxEvent.DEAD).update(
            status=OutboxEvent.DEAD, completed_at=now,
        )
    else:
        OutboxEvent.objects.filter(pk=event_id).exclude(status=OutboxEvent.PENDING).update(
            status=OutboxEvent.PENDING, completed_at=None,
        )


def _record_failure(delivery, token, exc, permanent) -> None:
    """Écriture séparée de l'annulation : erreur, nouvelle échéance ou passage en `dead`. Elle
    est conditionnée au jeton, pour ne pas écraser l'état posé par une autre exécution."""
    attempts = OutboxDelivery.objects.filter(pk=delivery.pk, locked_by=token).values_list('attempts', flat=True).first()
    if attempts is None:
        return
    dead = permanent or attempts >= _max_attempts()
    values = {'last_error': _describe(exc), 'locked_by': '', 'locked_at': None}
    if dead:
        values.update(status=OutboxDelivery.DEAD)
        logger.error("Outbox : livraison %s en échec définitif (%s).", delivery.pk, values['last_error'])
    else:
        values.update(status=OutboxDelivery.PENDING, next_attempt_at=timezone.now() + _backoff(attempts))
    OutboxDelivery.objects.filter(pk=delivery.pk, locked_by=token).update(**values)


def _process(pk, seen_status, seen_locked_by, now) -> Optional[bool]:
    """Traite une livraison. True = traitée, False = échec enregistré, None = non prise en charge."""
    token = _claim(pk, seen_status, seen_locked_by, now)
    if token is None:
        return None
    delivery = OutboxDelivery.objects.select_related('event').get(pk=pk)
    event = delivery.event
    subscriber = registry.get_subscriber(delivery.handler)
    try:
        if subscriber is None:
            raise PermanentEventError("handler inconnu")
        if event.version not in subscriber.versions:
            raise PermanentEventError(f"version {event.version} non prise en charge")
        data = EventData(
            id=event.pk, event_type=event.event_type, version=event.version, payload=event.payload,
            created_at=event.created_at,
        )
        # Effet de l'abonné et marque « traitée » validés ensemble : exactement une fois.
        with transaction.atomic():
            subscriber.func(data)
            marked = OutboxDelivery.objects.filter(
                pk=pk, locked_by=token, status=OutboxDelivery.PROCESSING,
            ).update(
                status=OutboxDelivery.DONE, processed_at=timezone.now(), last_error='', locked_by='', locked_at=None,
            )
            if not marked:
                raise OutboxError("verrou perdu : traitement annulé")
    except PermanentEventError as exc:
        _record_failure(delivery, token, exc, permanent=True)
        outcome = False
    except Exception as exc:  # un abonné ne doit jamais interrompre la diffusion des autres
        if not isinstance(exc, OutboxError):
            logger.exception("Outbox : échec de l'abonné %s (livraison %s).", delivery.handler, pk)
        _record_failure(delivery, token, exc, permanent=False)
        outcome = False
    else:
        outcome = True
    _refresh_event_status(event.pk)
    return outcome


def _run(queryset, limit, max_seconds) -> dict:
    started = time.monotonic()
    now = timezone.now()
    rows = list(
        queryset.filter(_due_filter(now)).order_by('event__created_at', 'created_at')
        .values_list('pk', 'status', 'locked_by')[:limit]
    )
    result = {'done': 0, 'failed': 0, 'skipped': 0}
    for pk, status, locked_by in rows:
        if max_seconds is not None and time.monotonic() - started > max_seconds:
            break
        try:
            outcome = _process(pk, status, locked_by, now)
        except OperationalError:
            logger.warning("Outbox : livraison %s reportée (base occupée).", pk)
            outcome = None
        key = 'skipped' if outcome is None else ('done' if outcome else 'failed')
        result[key] += 1
    return result


def dispatch_due(*, limit=200, max_seconds=None) -> dict:
    """Diffuse les livraisons échues (commande `dispatch_outbox`). Renvoie les décomptes."""
    return _run(OutboxDelivery.objects.all(), limit, max_seconds)


def dispatch_for_event(event_id) -> None:
    """Diffusion immédiate des livraisons d'un événement après validation de la transaction
    émettrice. Les exceptions sont journalisées : le cron reste le filet de sécurité."""
    try:
        _run(OutboxDelivery.objects.filter(event_id=event_id), limit=50, max_seconds=None)
    except Exception:
        logger.exception("Outbox : diffusion immédiate de l'événement %s échouée.", event_id)


def get_stats() -> dict:
    """Décompte des livraisons par statut et date de la plus ancienne en attente."""
    counts = {status: 0 for status, _ in OutboxDelivery.STATUS_CHOICES}
    for status in OutboxDelivery.objects.values_list('status', flat=True):
        counts[status] += 1
    oldest = OutboxDelivery.objects.filter(status=OutboxDelivery.PENDING).aggregate(m=Min('created_at'))['m']
    return {'counts': counts, 'oldest_pending_at': oldest}


def requeue(deliveries) -> list:
    """Remet des livraisons en attente (tentatives à zéro) ; renvoie celles qui ont été relancées
    (seulement `dead` ou `pending`, jamais une livraison traitée ou en cours). Acte sensible :
    l'appelant le journalise dans l'AuditLog."""
    now = timezone.now()
    requeued = []
    for delivery in deliveries:
        updated = OutboxDelivery.objects.filter(
            pk=delivery.pk, status__in=(OutboxDelivery.DEAD, OutboxDelivery.PENDING),
        ).update(
            status=OutboxDelivery.PENDING, attempts=0, next_attempt_at=now, locked_by='', locked_at=None,
            last_error='',
        )
        if updated:
            requeued.append(delivery)
            _refresh_event_status(delivery.event_id)
    return requeued


# --- Purge -------------------------------------------------------------------------

def purge(now=None) -> dict:
    """Supprime par lots les événements traités (OUTBOX_RETENTION_DAYS) et en échec définitif
    (OUTBOX_DEAD_RETENTION_DAYS). Les livraisons partent en cascade."""
    now = now or timezone.now()
    removed = {}
    for status, days in ((OutboxEvent.DONE, settings.OUTBOX_RETENTION_DAYS),
                         (OutboxEvent.DEAD, settings.OUTBOX_DEAD_RETENTION_DAYS)):
        cutoff = now - timedelta(days=days)
        total = 0
        while True:
            ids = list(
                OutboxEvent.objects.filter(status=status, completed_at__lt=cutoff)
                .values_list('pk', flat=True)[:PURGE_BATCH_SIZE]
            )
            if not ids:
                break
            OutboxEvent.objects.filter(pk__in=ids).delete()
            total += len(ids)
        removed[status] = total
    return removed
