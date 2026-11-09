"""Interface publique du domaine `visibility` : aucun autre domaine ne lit ses modèles.

Les fonctions reçoivent des identifiants (UUID) et des valeurs simples, jamais des instances
d'un autre domaine : `visibility` ne dépend d'aucun autre module métier.
"""
import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.common.contexts import CONTEXT_PROVIDER, CONTEXT_USER
from apps.common.utils import parse_uuid
from apps.moderation.services import record_audit
from apps.platform_core.registry import PermanentEventError
from apps.platform_core.services import publish_event

from .models import DailyVisibilityCounter, OfferUniqueView, RankingSettings, VisibilitySettings

# Fenêtres de l'historique et de la tendance (CDC 3.8, 3.9).
HISTORY_DAYS = 30
TRENDING_REFERENCE_DAYS = 7
TRENDING_MIN_VIEWS_TODAY = 5
TRENDING_GROWTH_FACTOR = 2


@dataclass(frozen=True)
class DailyViews:
    date: date
    views: int


@dataclass(frozen=True)
class SellerStats:
    history: list  # list[DailyViews]
    total_views: int
    today_views: int
    contacts_count: int


def build_viewer_key(user, anon_fingerprint) -> str:
    """Clé d'unicité d'une vue. L'empreinte anonyme vient d'un cookie contrôlé par le client :
    elle est hachée, ce qui borne la longueur et évite d'écrire une valeur arbitraire."""
    if user is not None and getattr(user, 'is_authenticated', False):
        return f"user:{user.pk}"
    digest = hashlib.sha256(str(anon_fingerprint).encode('utf-8')).hexdigest()[:32]
    return f"anon:{digest}"


def record_view(
    *, offer_id, seller_context_type, seller_context_id, viewer_key: str, day: Optional[date] = None,
) -> bool:
    """Enregistre une vue unique (offre, jour, visiteur). Renvoie True si elle est nouvelle.
    Une vue nouvelle publie `visibility.offer_viewed` dans la même transaction : le total de
    l'offre et son score sont recalculés par l'abonné de `marketplace`."""
    day = day or timezone.localdate()
    with transaction.atomic():
        _, is_new = OfferUniqueView.objects.get_or_create(offer_id=offer_id, date=day, viewer_key=viewer_key)
        if not is_new:
            return False
        _increment_counter(offer_id, seller_context_type, seller_context_id, day, 'views')
        publish_event(
            'visibility.offer_viewed', aggregate_type='offer', aggregate_id=offer_id,
            payload={'offer_id': str(offer_id), 'date': day.isoformat()},
        )
    return True


def _increment_counter(offer_id, seller_context_type, seller_context_id, day, field) -> None:
    counter, _ = DailyVisibilityCounter.objects.get_or_create(
        offer_id=offer_id, date=day,
        defaults={'seller_context_type': seller_context_type, 'seller_context_id': seller_context_id},
    )
    DailyVisibilityCounter.objects.filter(pk=counter.pk).update(**{field: F(field) + 1})


SHARE_KEY_PREFIX = 'share:'


def record_share(
    *, offer_id, seller_context_type, seller_context_id, actor_key: str, day: Optional[date] = None,
) -> bool:
    """Un partage compte une fois par (offre, utilisateur, jour). Renvoie True s'il est nouveau.
    L'unicité de la journée s'appuie sur OfferUniqueView (clé préfixée « share: », purgée comme
    les vues) ; le total durable est le compteur journalier `shares`, qui survit à cette purge.
    Un partage nouveau publie `visibility.offer_shared` dans la même transaction."""
    day = day or timezone.localdate()
    with transaction.atomic():
        _, is_new = OfferUniqueView.objects.get_or_create(
            offer_id=offer_id, date=day, viewer_key=f"{SHARE_KEY_PREFIX}{actor_key}"[:64],
        )
        if not is_new:
            return False
        _increment_counter(offer_id, seller_context_type, seller_context_id, day, 'shares')
        publish_event(
            'visibility.offer_shared', aggregate_type='offer', aggregate_id=offer_id,
            payload={'offer_id': str(offer_id), 'date': day.isoformat()},
        )
    return True


def total_views(offer_id) -> int:
    """Total des vues uniques d'une offre (somme des compteurs journaliers)."""
    return DailyVisibilityCounter.objects.filter(offer_id=offer_id).aggregate(total=Sum('views'))['total'] or 0


def total_shares(offer_id) -> int:
    """Total des partages d'une offre (somme des compteurs journaliers)."""
    return DailyVisibilityCounter.objects.filter(offer_id=offer_id).aggregate(total=Sum('shares'))['total'] or 0


def purge_unique_views(retention_days: Optional[int] = None, today: Optional[date] = None) -> int:
    """Supprime les vues uniques plus anciennes que la durée de conservation réglée en
    back-office. Les compteurs agrégés (DailyVisibilityCounter) ne sont pas touchés."""
    if retention_days is None:
        retention_days = VisibilitySettings.get_solo().unique_view_retention_days
    today = today or timezone.localdate()
    deleted, _ = OfferUniqueView.objects.filter(date__lt=today - timedelta(days=retention_days)).delete()
    return deleted


def get_ranking_settings() -> RankingSettings:
    return RankingSettings.get_solo()


def get_proximity_weights() -> tuple:
    """Coefficients de proximité D (même commune, même ville, défaut), lus en base. Appliqués à
    la lecture (tri) par le domaine `marketplace`."""
    row = get_ranking_settings()
    return row.proximity_same_commune, row.proximity_same_city, row.proximity_default


def compute_score(
    *, views, favorites, contacts, shares, created_at: datetime,
    settings_row: Optional[RankingSettings] = None, now: Optional[datetime] = None,
) -> float:
    """CDC 3.5 : score organique stocké = E x R (P = 1 ; D est appliqué à la lecture).

    - E, engagement : 1 + ln(1 + w_vues.vues + w_favoris.favoris + w_contacts.contacts + w_partages.partages) ;
    - R, récence : 0,5 ** (âge_heures / demi-vie), demi-vie réglable (72 h par défaut).

    Aucun terme de note, de confiance ni de promotion (règles 4 et 5). Toutes les pondérations
    viennent de `RankingSettings`. R est calculé au moment de l'appel."""
    row = settings_row or get_ranking_settings()
    now = now or timezone.now()

    engagement_raw = (
        row.weight_views * views + row.weight_favorites * favorites
        + row.weight_contacts * contacts + row.weight_shares * shares
    )
    engagement = 1 + math.log(1 + engagement_raw)

    age_hours = max((now - created_at).total_seconds() / 3600, 0.0)
    recency = 0.5 ** (age_hours / row.recency_half_life_hours)
    return engagement * recency


def trending_offer_ids(offer_ids: Iterable, today: Optional[date] = None) -> set:
    """CDC 3.8 : badge « Tendance » sur forte hausse d'engagement sur 24 h. Le CDC ne fixe pas
    de seuil exact ; heuristique à ajuster avec le maître d'ouvrage : au moins 5 vues
    aujourd'hui, et au moins le double de la moyenne quotidienne des 7 jours précédents.
    Une seule requête pour toute la liste."""
    ids = {i for i in offer_ids if i}
    if not ids:
        return set()
    today = today or timezone.localdate()
    week_ago = today - timedelta(days=TRENDING_REFERENCE_DAYS)
    rows = DailyVisibilityCounter.objects.filter(offer_id__in=ids, date__gte=week_ago).values_list(
        'offer_id', 'date', 'views',
    )
    previous, today_views = {}, {}
    for offer_id, day, views in rows:
        if day == today:
            today_views[offer_id] = views
        elif day < today:
            previous.setdefault(offer_id, []).append(views)

    trending = set()
    for offer_id, history in previous.items():
        average = sum(history) / len(history)
        views_today = today_views.get(offer_id, 0)
        if views_today >= TRENDING_MIN_VIEWS_TODAY and average > 0 and views_today >= TRENDING_GROWTH_FACTOR * average:
            trending.add(offer_id)
    return trending


def get_seller_stats(seller_context_type, seller_context_id, today: Optional[date] = None) -> SellerStats:
    """Historique de vues des 30 derniers jours et totaux d'un contexte vendeur (CDC 3.9)."""
    today = today or timezone.localdate()
    since = today - timedelta(days=HISTORY_DAYS)
    counters = DailyVisibilityCounter.objects.filter(
        seller_context_type=seller_context_type, seller_context_id=seller_context_id,
    )

    history = [
        DailyViews(date=row['date'], views=row['views'])
        for row in counters.filter(date__gte=since).values('date').annotate(views=Sum('views')).order_by('date')
    ]
    totals = counters.aggregate(views=Sum('views'), contacts=Sum('contacts'))
    today_views = counters.filter(date=today).aggregate(v=Sum('views'))['v'] or 0
    return SellerStats(
        history=history,
        total_views=totals['views'] or 0,
        today_views=today_views,
        contacts_count=totals['contacts'] or 0,
    )


def get_offer_history(offer_id, today: Optional[date] = None) -> list:
    """Historique de vues d'une offre sur 30 jours (liste de DailyViews)."""
    today = today or timezone.localdate()
    since = today - timedelta(days=HISTORY_DAYS)
    rows = DailyVisibilityCounter.objects.filter(offer_id=offer_id, date__gte=since).order_by('date')
    return [DailyViews(date=row.date, views=row.views) for row in rows]


def set_daily_contacts(day: date, rows: Iterable) -> int:
    """Fixe le nombre de contacts reçus un jour donné. `rows` : (offer_id, type du contexte vendeur,
    id du contexte vendeur, total)."""
    count = 0
    for offer_id, context_type, context_id, total in rows:
        DailyVisibilityCounter.objects.update_or_create(
            offer_id=offer_id, date=day,
            defaults={'seller_context_type': context_type, 'seller_context_id': context_id, 'contacts': total},
        )
        count += 1
    return count


def delete_offer_data(offer_ids: Iterable) -> None:
    """Efface les compteurs et vues uniques d'offres supprimées définitivement."""
    ids = [i for i in offer_ids if i]
    if not ids:
        return
    DailyVisibilityCounter.objects.filter(offer_id__in=ids).delete()
    OfferUniqueView.objects.filter(offer_id__in=ids).delete()


def purge_seller_context(context_type, context_id) -> int:
    """Efface les compteurs journaliers d'un contexte vendeur supprimé (T9-3, règle 10) ; les vues uniques de ses
    offres partent avec les offres (`delete_offer_data`). Idempotent. Journalise sans donnée personnelle si des lignes
    existaient. Renvoie le nombre de compteurs supprimés."""
    parsed = parse_uuid(context_id)
    if context_type not in (CONTEXT_USER, CONTEXT_PROVIDER) or parsed is None:
        raise PermanentEventError("charge utile invalide")
    with transaction.atomic():
        deleted, _ = DailyVisibilityCounter.objects.filter(
            seller_context_type=context_type, seller_context_id=parsed,
        ).delete()
        if deleted:
            record_audit(
                None, 'SELLER_CONTEXT_PURGED_VISIBILITY', details=f"counters={deleted}", context=(context_type, parsed),
            )
    return deleted
