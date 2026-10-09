import { useState } from "react";
import { Flag, Loader2, MessageSquareReply, MoreHorizontal, Pencil, Star, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Review, Uuid } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/common/StateViews";
import { UserAvatar } from "@/components/common/UserAvatar";
import { useReportFakeContact, useReviewEligibility, useReviewMutations, useReviews } from "@/hooks/use-reviews";
import { formatRelativeDate } from "@/lib/format";
import { reviewErrorMessage } from "@/lib/review-errors";
import { REVIEW_MAX_LENGTH } from "@/lib/review-validation";
import { cn } from "@/lib/utils";
import { ReviewEligibilityPanel } from "./ReviewEligibility";
import { ReviewForm } from "./ReviewForm";

const INITIAL_VISIBLE = 5;
const REPORT_MAX_LENGTH = 1000;

function Stars({ value, label }: { value: number; label: string }) {
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground" role="img" aria-label={label}>
      <span className="flex gap-0.5" aria-hidden>
        {[1, 2, 3, 4, 5].map((star) => (
          <Star key={star} className={cn("h-3.5 w-3.5", star <= value ? "fill-sun text-sun" : "text-muted-foreground/30")} />
        ))}
      </span>
    </span>
  );
}

interface ReviewsSectionProps {
  postId: Uuid;
  /** Le visiteur est le vendeur de l'offre. */
  isOwner: boolean;
  currentUserId?: Uuid;
  sellerName: string;
}

/** Avis après contact : liste, droit d'avis (éligibilité serveur), formulaire, réponse du vendeur et signalement. */
export function ReviewsSection({ postId, isOwner, currentUserId, sellerName }: ReviewsSectionProps) {
  const { t } = useTranslation();
  const reviewsQuery = useReviews(postId);
  const reviews = reviewsQuery.data ?? [];
  const eligibility = useReviewEligibility(postId, currentUserId, !isOwner);
  const { create, edit, remove, reply } = useReviewMutations(postId);
  const report = useReportFakeContact();

  const [showAll, setShowAll] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Review | null>(null);
  const [replyingTo, setReplyingTo] = useState<Review | null>(null);
  const [replyText, setReplyText] = useState("");
  const [reporting, setReporting] = useState<Review | null>(null);
  const [reportText, setReportText] = useState("");
  const [deleting, setDeleting] = useState<Review | null>(null);

  const visible = showAll ? reviews : reviews.slice(0, INITIAL_VISIBLE);

  return (
    <section aria-labelledby="avis-titre" className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
      <h2 id="avis-titre" className="text-lg font-bold">
        {t("reviews.title")} {reviews.length > 0 && <span className="text-muted-foreground">({reviews.length})</span>}
      </h2>

      {!isOwner && (
        <ReviewEligibilityPanel
          postId={postId}
          eligibility={eligibility.data}
          isLoading={eligibility.isLoading}
          isError={eligibility.isError}
          onRetry={() => void eligibility.refetch()}
          onGiveReview={() => setCreating(true)}
        />
      )}

      {/* Liste */}
      {reviewsQuery.isLoading ? (
        <div className="mt-6 space-y-5" role="status" aria-busy>
          {[0, 1].map((i) => (
            <div key={i} className="flex gap-3">
              <Skeleton className="h-9 w-9 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-full" />
              </div>
            </div>
          ))}
        </div>
      ) : reviewsQuery.isError ? (
        <ErrorState
          className="mt-6 py-8"
          description={t("reviews.loadError")}
          onRetry={() => void reviewsQuery.refetch()}
          isRetrying={reviewsQuery.isRefetching}
        />
      ) : reviews.length === 0 ? (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          {t("reviews.empty")} {isOwner ? t("reviews.emptyOwner") : t("reviews.emptyVisitor")}
        </p>
      ) : (
        <ul className="mt-6 divide-y">
          {visible.map((review) => {
            const isAuthor = review.user_id === currentUserId;
            // can_edit : fenêtre ouverte, avis ni masqué ni signalé (sinon l'API répond 403)
            const canEdit = isAuthor && review.can_edit !== false;
            const canReply = isOwner && !review.reply_content;
            const hasMenu = canEdit || isOwner;
            return (
              <li key={review.id} className="flex gap-3 py-5 first:pt-0 last:pb-0">
                <UserAvatar name={review.user_name} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{review.user_name}</p>
                      <p className="text-xs font-medium text-primary" title={t("reviews.sourceHint")}>
                        {t("reviews.sourceContact")}
                      </p>
                    </div>
                    {hasMenu && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 rounded-full" aria-label={t("reviews.actions")}>
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="rounded-xl">
                          {canEdit && (
                            <>
                              <DropdownMenuItem className="gap-2" onSelect={() => setEditing(review)}>
                                <Pencil className="h-4 w-4" /> {t("reviews.edit")}
                              </DropdownMenuItem>
                              <DropdownMenuItem className="gap-2 text-destructive focus:text-destructive" onSelect={() => setDeleting(review)}>
                                <Trash2 className="h-4 w-4" /> {t("reviews.delete")}
                              </DropdownMenuItem>
                            </>
                          )}
                          {isOwner && (
                            <>
                              {canReply && (
                                <DropdownMenuItem
                                  className="gap-2"
                                  onSelect={() => {
                                    setReplyingTo(review);
                                    setReplyText("");
                                  }}
                                >
                                  <MessageSquareReply className="h-4 w-4" /> {t("reviews.reply")}
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuItem
                                className="gap-2"
                                onSelect={() => {
                                  setReporting(review);
                                  setReportText("");
                                }}
                              >
                                <Flag className="h-4 w-4" /> {t("reviews.report")}
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>

                  <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                    <span className="flex items-center gap-1.5 text-xs">
                      <span className="text-muted-foreground">{t("reviews.offerRating")}</span>
                      <Stars value={review.offer_rating} label={`${t("reviews.offerRating")} : ${review.offer_rating} ${t("rating.outOf")}`} />
                    </span>
                    <span className="flex items-center gap-1.5 text-xs">
                      <span className="text-muted-foreground">{t("reviews.sellerRating")}</span>
                      <Stars value={review.seller_rating} label={`${t("reviews.sellerRating")} : ${review.seller_rating} ${t("rating.outOf")}`} />
                    </span>
                    <time dateTime={review.created_at} className="text-xs text-muted-foreground">
                      {formatRelativeDate(review.created_at)}
                    </time>
                    {review.edited_at && <span className="text-xs italic text-muted-foreground">({t("reviews.edited")})</span>}
                  </div>

                  <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-foreground/90">{review.content}</p>
                  {isAuthor && review.can_edit === false && <p className="mt-2 text-xs text-muted-foreground">{t("reviews.locked")}</p>}

                  {review.reply_content && (
                    <div className="mt-3 rounded-xl border-l-2 border-primary bg-primary/5 p-3">
                      <p className="text-xs font-semibold text-primary">{t("reviews.replyFrom", { name: sellerName })}</p>
                      <p className="mt-1 whitespace-pre-line text-sm text-foreground/90">{review.reply_content}</p>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {reviews.length > INITIAL_VISIBLE && (
        <Button variant="outline" className="mt-5 w-full" onClick={() => setShowAll((v) => !v)}>
          {showAll ? t("reviews.showLess") : t("reviews.showAll", { count: reviews.length })}
        </Button>
      )}

      {/* Donner mon avis */}
      <Dialog
        open={creating}
        onOpenChange={(open) => {
          setCreating(open);
          if (!open) create.reset();
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto rounded-2xl sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("reviews.formTitle")}</DialogTitle>
            <DialogDescription>{t("reviews.formIntro")}</DialogDescription>
          </DialogHeader>
          <ReviewForm
            submitLabel={t("reviews.submit")}
            isPending={create.isPending}
            error={create.isError ? reviewErrorMessage(create.error) : null}
            onSubmit={(input) => create.mutate(input, { onSuccess: () => setCreating(false) })}
            onCancel={() => setCreating(false)}
          />
        </DialogContent>
      </Dialog>

      {/* Modifier un avis */}
      <Dialog
        open={!!editing}
        onOpenChange={(open) => {
          if (!open) {
            setEditing(null);
            edit.reset();
          }
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto rounded-2xl sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("reviews.editTitle")}</DialogTitle>
            <DialogDescription>{t("reviews.formIntro")}</DialogDescription>
          </DialogHeader>
          {editing && (
            <ReviewForm
              key={editing.id}
              initial={editing}
              submitLabel={t("reviews.save")}
              isPending={edit.isPending}
              error={edit.isError ? reviewErrorMessage(edit.error) : null}
              onSubmit={(input) => edit.mutate({ id: editing.id, ...input }, { onSuccess: () => setEditing(null) })}
              onCancel={() => setEditing(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Réponse du vendeur */}
      <Dialog
        open={!!replyingTo}
        onOpenChange={(open) => {
          if (!open) {
            setReplyingTo(null);
            reply.reset();
          }
        }}
      >
        <DialogContent className="rounded-2xl sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("reviews.replyTitle", { name: replyingTo?.user_name })}</DialogTitle>
            <DialogDescription className="sr-only">{t("reviews.replyLabel")}</DialogDescription>
          </DialogHeader>
          <blockquote className="rounded-xl bg-muted p-3 text-sm italic text-muted-foreground">{replyingTo?.content}</blockquote>
          <Textarea
            value={replyText}
            onChange={(e) => setReplyText(e.target.value.slice(0, REVIEW_MAX_LENGTH))}
            placeholder={t("reviews.replyPlaceholder")}
            className="min-h-[110px] rounded-xl"
            aria-label={t("reviews.replyLabel")}
          />
          {reply.isError && (
            <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {reviewErrorMessage(reply.error)}
            </p>
          )}
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setReplyingTo(null)}>
              {t("reviews.cancel")}
            </Button>
            <Button
              disabled={reply.isPending || !replyText.trim()}
              onClick={() =>
                replyingTo &&
                reply.mutate({ id: replyingTo.id, reply_content: replyText.trim() }, { onSuccess: () => setReplyingTo(null) })
              }
            >
              {reply.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t("reviews.replySubmit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Signalement « contact fictif » */}
      <Dialog
        open={!!reporting}
        onOpenChange={(open) => {
          if (!open) {
            setReporting(null);
            report.reset();
          }
        }}
      >
        <DialogContent className="rounded-2xl sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("reviews.reportTitle")}</DialogTitle>
            <DialogDescription>{t("reviews.reportIntro")}</DialogDescription>
          </DialogHeader>
          <Textarea
            value={reportText}
            onChange={(e) => setReportText(e.target.value.slice(0, REPORT_MAX_LENGTH))}
            className="min-h-[90px] rounded-xl"
            aria-label={t("reviews.reportLabel")}
            placeholder={t("reviews.reportLabel")}
          />
          {report.isError && (
            <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {reviewErrorMessage(report.error)}
            </p>
          )}
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setReporting(null)}>
              {t("reviews.cancel")}
            </Button>
            <Button
              disabled={report.isPending}
              onClick={() =>
                reporting && report.mutate({ reviewId: reporting.id, description: reportText.trim() }, { onSuccess: () => setReporting(null) })
              }
            >
              {report.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t("reviews.reportSubmit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Suppression */}
      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>{t("reviews.deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("reviews.deleteDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("reviews.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              {t("reviews.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
