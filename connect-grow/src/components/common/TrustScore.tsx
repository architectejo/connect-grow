import { Sparkles, Star } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatRating } from "@/lib/format";
import type { TrustInfo } from "@/lib/trust";
import { cn } from "@/lib/utils";

interface TrustScoreProps {
  trust: Pick<TrustInfo, "score" | "reviewsCount" | "isNew">;
  size?: "sm" | "md" | "lg";
  /** Afficher le nombre d'avis à côté de la note. */
  showCount?: boolean;
  /** Libellé court (« Nouveau ») pour les espaces étroits comme les cartes d'annonce. */
  compact?: boolean;
  className?: string;
}

const sizes = {
  sm: { text: "text-xs", star: "h-3.5 w-3.5" },
  md: { text: "text-sm", star: "h-4 w-4" },
  lg: { text: "text-base", star: "h-5 w-5" },
};

/**
 * Note de confiance du vendeur. En dessous de 3 avis, affiche « Nouveau vendeur »
 * plutôt qu'une note trompeuse (cahier des charges 3.7).
 */
export function TrustScore({ trust, size = "sm", showCount = true, compact, className }: TrustScoreProps) {
  const { t } = useTranslation();
  const s = sizes[size];

  if (trust.isNew || trust.score === null) {
    return (
      <span
        className={cn("inline-flex items-center gap-1 whitespace-nowrap font-medium text-info", s.text, className)}
        title={compact ? t("trust.newSeller") : undefined}
      >
        <Sparkles className={s.star} aria-hidden />
        {compact ? (
          <>
            {t("trust.newSellerShort")}
            <span className="sr-only"> {t("trust.newSellerSuffix")}</span>
          </>
        ) : (
          t("trust.newSeller")
        )}
      </span>
    );
  }

  const score = formatRating(trust.score);

  return (
    <span
      className={cn("inline-flex items-center gap-1", s.text, className)}
      aria-label={t("trust.ratingLabel", { score })}
    >
      <Star className={cn(s.star, "fill-sun text-sun")} aria-hidden />
      <span className="font-bold tabular-nums text-foreground">{score}</span>
      {showCount && trust.reviewsCount !== undefined && (
        <span className="text-muted-foreground">({t("trust.reviews", { count: trust.reviewsCount })})</span>
      )}
    </span>
  );
}
