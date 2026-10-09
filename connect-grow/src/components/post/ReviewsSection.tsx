import { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Lock, MessageSquareReply, MoreHorizontal, Pencil, Star, Trash2 } from "lucide-react";
import type { Review } from "@/api/types";
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
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { UserAvatar } from "@/components/common/UserAvatar";
import { useReviewMutations, useReviews } from "@/hooks/use-reviews";
import { loginPath } from "@/lib/auth-paths";
import { formatRating, formatRelativeDate } from "@/lib/format";
import { cn } from "@/lib/utils";

// CDC 3.7 : commentaire de 10 à 500 caractères
const MIN_LENGTH = 10;
const MAX_LENGTH = 500;
const INITIAL_VISIBLE = 5;

function Stars({ value, size = "h-4 w-4" }: { value: number; size?: string }) {
  return (
    <span className="flex gap-0.5" aria-label={`${value} sur 5`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <Star key={star} className={cn(size, star <= Math.round(value) ? "fill-sun text-sun" : "text-muted-foreground/30")} aria-hidden />
      ))}
    </span>
  );
}

function StarInput({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const labels = ["Très mauvais", "Mauvais", "Correct", "Bien", "Excellent"];
  return (
    <div role="radiogroup" aria-label="Votre note" className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          role="radio"
          aria-checked={star === value}
          aria-label={`${star} étoile${star > 1 ? "s" : ""} : ${labels[star - 1]}`}
          onClick={() => onChange(star)}
          className="rounded-md p-0.5 transition-transform hover:scale-110"
        >
          <Star className={cn("h-7 w-7", star <= value ? "fill-sun text-sun" : "text-muted-foreground/30")} aria-hidden />
        </button>
      ))}
      <span className="ml-2 text-sm font-medium text-muted-foreground">{labels[value - 1]}</span>
    </div>
  );
}

function ReviewTextarea({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const length = value.trim().length;
  return (
    <div className="space-y-1.5">
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, MAX_LENGTH))}
        placeholder={placeholder}
        className="min-h-[110px] rounded-xl"
        aria-label="Votre commentaire"
      />
      <p className={cn("text-right text-xs", length > 0 && length < MIN_LENGTH ? "text-destructive" : "text-muted-foreground")}>
        {length < MIN_LENGTH ? `${MIN_LENGTH} caractères minimum · ` : ""}
        {value.length}/{MAX_LENGTH}
      </p>
    </div>
  );
}

const isValidComment = (text: string) => text.trim().length >= MIN_LENGTH;

interface ReviewsSectionProps {
  postId: number;
  isOwner: boolean;
  isAuthenticated: boolean;
  currentUserId?: number;
  sellerName: string;
}

export function ReviewsSection({ postId, isOwner, isAuthenticated, currentUserId, sellerName }: ReviewsSectionProps) {
  const { data: reviews = [], isLoading } = useReviews(postId);
  const { create, edit, remove, reply } = useReviewMutations(postId);

  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState<Review | null>(null);
  const [editRating, setEditRating] = useState(5);
  const [editComment, setEditComment] = useState("");
  const [replyingTo, setReplyingTo] = useState<Review | null>(null);
  const [replyText, setReplyText] = useState("");
  const [deleting, setDeleting] = useState<Review | null>(null);

  const hasReviewed = reviews.some((r) => r.user_id === currentUserId);
  const average = reviews.length ? reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length : 0;
  const distribution = [5, 4, 3, 2, 1].map((star) => ({ star, count: reviews.filter((r) => r.rating === star).length }));
  const visible = showAll ? reviews : reviews.slice(0, INITIAL_VISIBLE);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValidComment(comment)) return;
    create.mutate({ content: comment.trim(), rating }, { onSuccess: () => { setComment(""); setRating(5); } });
  };

  return (
    <section aria-labelledby="avis-titre" className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
      <h2 id="avis-titre" className="text-lg font-bold">
        Avis {reviews.length > 0 && <span className="text-muted-foreground">({reviews.length})</span>}
      </h2>

      {reviews.length > 0 && (
        <div className="mt-5 grid gap-6 rounded-xl bg-muted/60 p-4 sm:grid-cols-[auto_1fr] sm:items-center">
          <div className="text-center sm:px-4">
            <p className="font-display text-4xl font-extrabold tabular-nums">{formatRating(average)}</p>
            <Stars value={average} />
            <p className="mt-1 text-xs text-muted-foreground">{reviews.length} avis</p>
          </div>
          <ul className="space-y-1.5" aria-label="Répartition des notes">
            {distribution.map(({ star, count }) => (
              <li key={star} className="flex items-center gap-2 text-xs">
                <span className="w-3 font-semibold tabular-nums">{star}</span>
                <Star className="h-3 w-3 fill-sun text-sun" aria-hidden />
                <span className="h-2 flex-1 overflow-hidden rounded-full bg-background">
                  <span className="block h-full rounded-full bg-sun" style={{ width: `${(count / reviews.length) * 100}%` }} />
                </span>
                <span className="w-5 text-right tabular-nums text-muted-foreground">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Formulaire */}
      {!isAuthenticated ? (
        <div className="mt-5 flex flex-col items-center gap-3 rounded-xl border border-dashed p-6 text-center">
          <Lock className="h-6 w-6 text-muted-foreground/60" aria-hidden />
          <p className="text-sm text-muted-foreground">Connectez-vous pour donner votre avis sur ce vendeur.</p>
          <Button asChild variant="outline" size="sm">
            <Link to={loginPath(`/post/${postId}`)}>Se connecter</Link>
          </Button>
        </div>
      ) : !isOwner && !hasReviewed ? (
        <form onSubmit={submit} className="mt-5 space-y-3 rounded-xl border p-4">
          <p className="text-sm font-semibold">Votre expérience avec ce vendeur</p>
          <StarInput value={rating} onChange={setRating} />
          <ReviewTextarea value={comment} onChange={setComment} placeholder="Produit conforme ? Vendeur ponctuel ? Racontez." />
          <div className="flex justify-end">
            <Button type="submit" disabled={create.isPending || !isValidComment(comment)}>
              {create.isPending && <Loader2 className="animate-spin" aria-hidden />}
              Publier mon avis
            </Button>
          </div>
        </form>
      ) : null}

      {/* Liste */}
      {isLoading ? (
        <div className="mt-6 space-y-5">
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
      ) : reviews.length === 0 ? (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Aucun avis pour le moment. {isOwner ? "Ils apparaîtront ici." : "Soyez le premier à partager votre expérience."}
        </p>
      ) : (
        <ul className="mt-6 divide-y">
          {visible.map((review) => {
            const isAuthor = review.user_id === currentUserId;
            return (
              <li key={review.id} className="flex gap-3 py-5 first:pt-0 last:pb-0">
                <UserAvatar name={review.user_name} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{review.user_name}</p>
                      <div className="mt-0.5 flex items-center gap-2">
                        <Stars value={review.rating} size="h-3.5 w-3.5" />
                        <time dateTime={review.created_at} className="text-xs text-muted-foreground">
                          {formatRelativeDate(review.created_at)}
                        </time>
                      </div>
                    </div>
                    {(isAuthor || isOwner) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 rounded-full" aria-label="Actions sur l'avis">
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="rounded-xl">
                          {isAuthor && (
                            <>
                              <DropdownMenuItem
                                className="gap-2"
                                onSelect={() => {
                                  setEditing(review);
                                  setEditRating(review.rating);
                                  setEditComment(review.content);
                                }}
                              >
                                <Pencil className="h-4 w-4" /> Modifier
                              </DropdownMenuItem>
                              <DropdownMenuItem className="gap-2 text-destructive focus:text-destructive" onSelect={() => setDeleting(review)}>
                                <Trash2 className="h-4 w-4" /> Supprimer
                              </DropdownMenuItem>
                            </>
                          )}
                          {isOwner && (
                            <DropdownMenuItem
                              className="gap-2"
                              onSelect={() => {
                                setReplyingTo(review);
                                setReplyText(review.reply_content ?? "");
                              }}
                            >
                              <MessageSquareReply className="h-4 w-4" /> {review.reply_content ? "Modifier ma réponse" : "Répondre"}
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                  <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-foreground/90">{review.content}</p>

                  {review.reply_content && (
                    <div className="mt-3 rounded-xl border-l-2 border-primary bg-primary/5 p-3">
                      <p className="text-xs font-semibold text-primary">Réponse de {sellerName}</p>
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
          {showAll ? "Afficher moins" : `Voir les ${reviews.length} avis`}
        </Button>
      )}

      {/* Modifier un avis */}
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="rounded-2xl sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Modifier votre avis</DialogTitle>
          </DialogHeader>
          <StarInput value={editRating} onChange={setEditRating} />
          <ReviewTextarea value={editComment} onChange={setEditComment} />
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Annuler
            </Button>
            <Button
              disabled={edit.isPending || !isValidComment(editComment)}
              onClick={() =>
                editing &&
                edit.mutate(
                  { id: editing.id, content: editComment.trim(), rating: editRating },
                  { onSuccess: () => setEditing(null) },
                )
              }
            >
              {edit.isPending && <Loader2 className="animate-spin" aria-hidden />}
              Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Réponse du vendeur */}
      <Dialog open={!!replyingTo} onOpenChange={(open) => !open && setReplyingTo(null)}>
        <DialogContent className="rounded-2xl sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Répondre à {replyingTo?.user_name}</DialogTitle>
          </DialogHeader>
          <blockquote className="rounded-xl bg-muted p-3 text-sm italic text-muted-foreground">{replyingTo?.content}</blockquote>
          <Textarea
            value={replyText}
            onChange={(e) => setReplyText(e.target.value.slice(0, MAX_LENGTH))}
            placeholder="Votre réponse publique…"
            className="min-h-[110px] rounded-xl"
            aria-label="Votre réponse"
          />
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setReplyingTo(null)}>
              Annuler
            </Button>
            <Button
              disabled={reply.isPending || !replyText.trim()}
              onClick={() =>
                replyingTo &&
                reply.mutate({ id: replyingTo.id, reply_content: replyText.trim() }, { onSuccess: () => setReplyingTo(null) })
              }
            >
              {reply.isPending && <Loader2 className="animate-spin" aria-hidden />}
              Publier la réponse
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Suppression */}
      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer votre avis ?</AlertDialogTitle>
            <AlertDialogDescription>Cette action est définitive.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
