import { useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReviewInput } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  REVIEW_MAX_LENGTH,
  REVIEW_MIN_LENGTH,
  isReviewDraftValid,
  reviewCommentLength,
  toReviewInput,
} from "@/lib/review-validation";
import { cn } from "@/lib/utils";
import { StarInput } from "./StarInput";

interface ReviewFormProps {
  initial?: Partial<ReviewInput>;
  submitLabel: string;
  isPending?: boolean;
  /** Message d'erreur du serveur (déjà traduit), affiché dans le formulaire. */
  error?: string | null;
  onSubmit: (input: ReviewInput) => void;
  onCancel?: () => void;
}

/** Formulaire d'avis : note de l'offre, note du vendeur et commentaire de 10 à 500 caractères. */
export function ReviewForm({ initial, submitLabel, isPending, error, onSubmit, onCancel }: ReviewFormProps) {
  const { t } = useTranslation();
  const commentId = useId();
  const [draft, setDraft] = useState({
    offer_rating: initial?.offer_rating ?? 0,
    seller_rating: initial?.seller_rating ?? 0,
    content: initial?.content ?? "",
  });
  const length = reviewCommentLength(draft.content);
  const valid = isReviewDraftValid(draft);
  const ratingsMissing = draft.offer_rating === 0 || draft.seller_rating === 0;

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !isPending) onSubmit(toReviewInput(draft));
      }}
    >
      <StarInput
        label={t("reviews.offerRating")}
        value={draft.offer_rating}
        onChange={(offer_rating) => setDraft((d) => ({ ...d, offer_rating }))}
        disabled={isPending}
      />
      <StarInput
        label={t("reviews.sellerRating")}
        value={draft.seller_rating}
        onChange={(seller_rating) => setDraft((d) => ({ ...d, seller_rating }))}
        disabled={isPending}
      />

      <div className="space-y-1.5">
        <label htmlFor={commentId} className="text-sm font-semibold">
          {t("reviews.commentLabel")}
        </label>
        <Textarea
          id={commentId}
          value={draft.content}
          onChange={(e) => setDraft((d) => ({ ...d, content: e.target.value.slice(0, REVIEW_MAX_LENGTH) }))}
          placeholder={t("reviews.commentPlaceholder")}
          className="min-h-[110px] rounded-xl"
          disabled={isPending}
          aria-describedby={`${commentId}-hint`}
        />
        <p
          id={`${commentId}-hint`}
          className={cn("text-right text-xs", length > 0 && length < REVIEW_MIN_LENGTH ? "text-destructive" : "text-muted-foreground")}
        >
          {length < REVIEW_MIN_LENGTH ? `${t("reviews.commentMin", { min: REVIEW_MIN_LENGTH })} · ` : ""}
          {draft.content.length}/{REVIEW_MAX_LENGTH}
        </p>
      </div>

      {ratingsMissing && <p className="text-xs text-muted-foreground">{t("reviews.chooseRatings")}</p>}
      {error && (
        <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={isPending}>
            {t("reviews.cancel")}
          </Button>
        )}
        <Button type="submit" disabled={isPending || !valid}>
          {isPending && <Loader2 className="animate-spin" aria-hidden />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
