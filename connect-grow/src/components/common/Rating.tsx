import type { ReactNode } from "react";
import { Star } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { RatingSummary } from "@/api/types";
import { useRatingAriaLabel, type RatingKind } from "@/hooks/use-rating-label";
import { formatRating } from "@/lib/format";
import { cn } from "@/lib/utils";

interface RatingValueProps {
  rating?: RatingSummary | null;
  kind: RatingKind;
  className?: string;
}

/**
 * Note en une ligne (cartes d'annonce). Sous le seuil d'affichage la moyenne est absente (null) :
 * on dit « Pas encore assez d'avis » mais le nombre d'avis reste affiché. Jamais de note neutre.
 */
export function RatingValue({ rating, kind, className }: RatingValueProps) {
  const { t } = useTranslation();
  const ariaLabel = useRatingAriaLabel();
  if (!rating) return null;

  return (
    <span
      role="img"
      aria-label={ariaLabel(rating, kind)}
      className={cn("inline-flex flex-wrap items-center gap-x-1 text-xs", className)}
    >
      {rating.average !== null ? (
        <>
          <Star className="h-3.5 w-3.5 fill-sun text-sun" aria-hidden />
          <span className="font-bold tabular-nums text-foreground" aria-hidden>
            {formatRating(rating.average)}
          </span>
          <span className="text-muted-foreground" aria-hidden>
            ({t("rating.count", { count: rating.count })})
          </span>
        </>
      ) : (
        <span className="text-muted-foreground" aria-hidden>
          {rating.count > 0
            ? `${t("rating.notEnough")} (${t("rating.count", { count: rating.count })})`
            : t("rating.none")}
        </span>
      )}
    </span>
  );
}

interface RatingBlockProps {
  rating?: RatingSummary | null;
  kind: RatingKind;
  /** Information complémentaire (ancienneté du vendeur…). */
  footer?: ReactNode;
  className?: string;
}

/** Bloc de note distinct : « Note de l'offre » ou « Note du vendeur ». Les deux ne sont jamais fusionnées. */
export function RatingBlock({ rating, kind, footer, className }: RatingBlockProps) {
  const { t } = useTranslation();
  const ariaLabel = useRatingAriaLabel();
  if (!rating) return null;

  return (
    <div className={cn("rounded-xl bg-muted/60 p-3", className)} data-testid={`rating-block-${kind}`}>
      <p className="text-xs font-medium text-muted-foreground" aria-hidden>
        {t(`rating.${kind}`)}
      </p>
      <div role="img" aria-label={ariaLabel(rating, kind)} className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
        {rating.average !== null ? (
          <>
            <span className="font-display text-2xl font-extrabold tabular-nums text-foreground" aria-hidden>
              {formatRating(rating.average)}
            </span>
            <span className="flex gap-0.5" aria-hidden>
              {[1, 2, 3, 4, 5].map((star) => (
                <Star
                  key={star}
                  className={cn("h-3.5 w-3.5", star <= Math.round(rating.average ?? 0) ? "fill-sun text-sun" : "text-muted-foreground/30")}
                />
              ))}
            </span>
            <span className="text-xs text-muted-foreground" aria-hidden>
              {t("rating.count", { count: rating.count })}
            </span>
          </>
        ) : (
          <span className="text-sm font-medium text-muted-foreground" aria-hidden>
            {rating.count > 0
              ? `${t("rating.notEnough")} (${t("rating.count", { count: rating.count })})`
              : t("rating.none")}
          </span>
        )}
      </div>
      {footer && <div className="mt-1 text-xs text-muted-foreground">{footer}</div>}
    </div>
  );
}
