import { useTranslation } from "react-i18next";
import type { RatingSummary } from "@/api/types";
import { formatRating } from "@/lib/format";

export type RatingKind = "offer" | "seller";

/** Libellé accessible : « Note de l'offre : 4,2 sur 5, 5 avis ». */
export function useRatingAriaLabel() {
  const { t } = useTranslation();
  return (rating: RatingSummary, kind: RatingKind): string => {
    const label = t(`rating.${kind}`);
    if (rating.average !== null) return t("rating.aria", { label, average: formatRating(rating.average), count: rating.count });
    if (rating.count > 0) return t("rating.ariaNotEnough", { label, count: rating.count });
    return t("rating.ariaNone", { label });
  };
}
