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

from .models import DailyVisibilityCounter, OfferUniqueView, RankingSettings

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


def record_view(*, offer_id, seller_id, viewer_key: str, day: Optional[date] = None) -> bool:
    """Enregistre une vue unique (offre, jour, visiteur). Renvoie True si elle est nouvelle."""
    day = day or timezone.now().date()
    with transaction.atomic():
        _, is_new = OfferUniqueView.objects.get_or_create(offer_id=offer_id, date=day, viewer_key=viewer_key)
        if not is_new:
            return False
        counter, _ = DailyVisibilityCounter.objects.get_or_create(
            offer_id=offer_id, date=day, defaults={'seller_id': seller_id},
        )
        DailyVisibilityCounter.objects.filter(pk=counter.pk).update(views=F('views') + 1)
    return True


def get_ranking_settings() -> RankingSettings:
    return RankingSettings.get_solo()


def compute_score(
    *, views, likes, comments, shares, created_at: datetime, trust_score: float,
    settings_row: Optional[RankingSettings] = None, now: Optional[datetime] = None,
) -> float:
    """CDC 3.8 : visibility_score = E . T . R . (1 + b)

    - E, engagement : 1 + ln(1 + w_v.vues + w_l.likes + w_c.commentaires + w_s.partages)
    - T, confiance : 0,8 + 0,4 . (TrustScore / 5), borné à [trust_factor_min, trust_factor_max]
      (retiré par L0-07 / L0-08)
    - R, récence : e^(-λ . âge_heures), avec une demi-vie paramétrable (72 h par défaut)
    - b, Boost : 0 tant que la promotion payante (lot 1) n'existe pas

    R est calculé au moment de l'appel ; aucun traitement de fond n'est requis."""
    row = settings_row or get_ranking_settings()
    now = now or timezone.now()

    engagement_raw = (
        row.weight_views * views + row.weight_likes * likes
        + row.weight_comments * comments + row.weight_shares * shares
    )
    engagement = 1 + math.log(1 + engagement_raw)

    trust_factor = 0.8 + 0.4 * (trust_score / 5.0)
    trust_factor = max(row.trust_factor_min, min(row.trust_factor_max, trust_factor))

    age_hours = (now - created_at).total_seconds() / 3600
    recency = math.exp(-(math.log(2) / row.recency_half_life_hours) * age_hours)

    boost = 0
    return engagement * trust_factor * recency * (1 + boost)


def trending_offer_ids(offer_ids: Iterable, today: Optional[date] = None) -> set:
    """CDC 3.8 : badge « Tendance » sur forte hausse d'engagement sur 24 h. Le CDC ne fixe pas
    de seuil exact ; heuristique à ajuster avec le maître d'ouvrage : au moins 5 vues
    aujourd'hui, et au moins le double de la moyenne quotidienne des 7 jours précédents.
    Une seule requête pour toute la liste."""
    ids = {i for i in offer_ids if i}
    if not ids:
        return set()
    today = today or timezone.now().date()
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


def get_seller_stats(seller_id, today: Optional[date] = None) -> SellerStats:
    """Historique de vues des 30 derniers jours et totaux d'un vendeur (CDC 3.9)."""
    today = today or timezone.now().date()
    since = today - timedelta(days=HISTORY_DAYS)
    counters = DailyVisibilityCounter.objects.filter(seller_id=seller_id)

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
    today = today or timezone.now().date()
    since = today - timedelta(days=HISTORY_DAYS)
    rows = DailyVisibilityCounter.objects.filter(offer_id=offer_id, date__gte=since).order_by('date')
    return [DailyViews(date=row.date, views=row.views) for row in rows]


def set_daily_contacts(day: date, rows: Iterable) -> int:
    """Fixe le nombre de contacts reçus un jour donné. `rows` : (offer_id, seller_id, total)."""
    count = 0
    for offer_id, seller_id, total in rows:
        DailyVisibilityCounter.objects.update_or_create(
            offer_id=offer_id, date=day, defaults={'seller_id': seller_id, 'contacts': total},
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
