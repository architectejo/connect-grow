import { Link } from "react-router-dom";
import { Lock, MessageSquareHeart, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReviewEligibility } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { loginPath } from "@/lib/auth-paths";
import { formatDateTime } from "@/lib/format";

interface ReviewEligibilityPanelProps {
  postId: string;
  eligibility?: ReviewEligibility;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onGiveReview: () => void;
}

/**
 * Zone « Donner mon avis ». L'état vient uniquement de GET /reviews/eligibility/ : le client ne déduit
 * jamais lui-même le droit d'avis. Le propriétaire de l'offre n'a rien à voir ici.
 */
export function ReviewEligibilityPanel({ postId, eligibility, isLoading, isError, onRetry, onGiveReview }: ReviewEligibilityPanelProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className="mt-5" role="status" aria-label={t("reviews.eligibility.loading")}>
        <Skeleton className="h-10 w-44 rounded-lg" />
      </div>
    );
  }

  if (isError || !eligibility) {
    return (
      <div role="alert" className="mt-5 flex flex-wrap items-center gap-3 rounded-xl border p-4 text-sm text-muted-foreground">
        <span>{t("reviews.eligibility.error")}</span>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw aria-hidden /> {t("states.retry")}
        </Button>
      </div>
    );
  }

  if (eligibility.can_review) {
    return (
      <div className="mt-5">
        <Button type="button" onClick={onGiveReview}>
          <MessageSquareHeart aria-hidden /> {t("reviews.give")}
        </Button>
      </div>
    );
  }

  switch (eligibility.reason) {
    case "login_required":
      return (
        <div className="mt-5 flex flex-col items-center gap-3 rounded-xl border border-dashed p-6 text-center">
          <Lock className="h-6 w-6 text-muted-foreground/60" aria-hidden />
          <p className="text-sm text-muted-foreground">{t("reviews.eligibility.login_required")}</p>
          <Button asChild variant="outline" size="sm">
            <Link to={loginPath(`/post/${postId}`)}>{t("reviews.eligibility.login")}</Link>
          </Button>
        </div>
      );
    case "too_early": {
      const date = eligibility.available_at ? formatDateTime(eligibility.available_at) : "";
      return (
        <p className="mt-5 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
          {date ? t("reviews.eligibility.too_early", { date }) : t("reviews.eligibility.too_earlyNoDate")}
        </p>
      );
    }
    case "no_contact":
    case "already_reviewed":
    case "offer_unavailable":
      return (
        <p className="mt-5 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
          {t(`reviews.eligibility.${eligibility.reason}`)}
        </p>
      );
    default:
      // own_offer (le vendeur ne note pas sa propre annonce) ou raison inconnue : rien à proposer
      return null;
  }
}
