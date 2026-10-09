import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient, { unwrapList } from "@/api/client";
import type { AuthorResponseResult, Review, ReviewEligibility, ReviewInput, Uuid } from "@/api/types";
import i18n from "@/i18n";
import { apiErrorCode, shouldRetryQuery } from "@/lib/errors";
import { reviewErrorMessage } from "@/lib/review-errors";
import { marketplaceKeys } from "./use-marketplace";

export const reviewKeys = {
  forPost: (postId: Uuid) => ["reviews", "post", postId] as const,
  // La réponse dépend du compte connecté : la clé le porte pour ne jamais mélanger deux sessions
  eligibility: (postId: Uuid, userId?: Uuid) => ["reviews", "eligibility", postId, userId ?? "anonymous"] as const,
  eligibilityOf: (postId: Uuid) => ["reviews", "eligibility", postId] as const,
};

const BASE = "interactions/reviews/";

export function useReviews(postId?: Uuid) {
  return useQuery({
    queryKey: reviewKeys.forPost(postId ?? ""),
    queryFn: async () => unwrapList<Review>((await apiClient.get(BASE, { params: { post: postId } })).data),
    enabled: !!postId,
    retry: shouldRetryQuery,
  });
}

/**
 * Droit d'avis sur une offre. Le serveur seul décide (jamais déduit côté client) :
 * le bouton « Donner mon avis » n'apparaît que si `can_review` est vrai.
 */
export function useReviewEligibility(postId?: Uuid, userId?: Uuid, enabled = true) {
  // L'endpoint est authentifié (401 pour un anonyme) : sans compte, on ne l'appelle pas
  enabled = enabled && !!userId;
  return useQuery({
    queryKey: reviewKeys.eligibility(postId ?? "", userId),
    queryFn: async () => (await apiClient.get<ReviewEligibility>(`${BASE}eligibility/`, { params: { post: postId } })).data,
    enabled: !!postId && enabled,
    retry: shouldRetryQuery,
  });
}

/** Codes d'erreur après lesquels l'éligibilité affichée n'est plus à jour. */
const ELIGIBILITY_CODES = new Set([
  "own_offer",
  "not_eligible",
  "contact_rejected",
  "review_too_early",
  "already_reviewed",
  "review_recently_deleted",
  "offer_unavailable",
]);

/** Création, modification, suppression et réponse du vendeur, avec rafraîchissement des listes et des notes. */
export function useReviewMutations(postId: Uuid) {
  const queryClient = useQueryClient();
  const key = reviewKeys.forPost(postId);
  const update = (fn: (reviews: Review[]) => Review[]) =>
    queryClient.setQueryData<Review[]>(key, (reviews) => fn(reviews ?? []));
  // Les moyennes sont calculées par le serveur à la lecture : on relit l'offre et les listes
  const refreshRatings = () => {
    void queryClient.invalidateQueries({ queryKey: marketplaceKeys.post(postId) });
    void queryClient.invalidateQueries({ queryKey: marketplaceKeys.postLists() });
  };
  const refreshEligibility = () => queryClient.invalidateQueries({ queryKey: reviewKeys.eligibilityOf(postId) });
  const onEligibilityError = (error: unknown) => {
    const code = apiErrorCode(error);
    if (code && ELIGIBILITY_CODES.has(code)) void refreshEligibility();
  };

  const create = useMutation({
    mutationFn: async (input: ReviewInput) => (await apiClient.post<Review>(BASE, { post: postId, ...input })).data,
    onSuccess: (review) => {
      update((reviews) => [review, ...reviews.filter((r) => r.id !== review.id)]);
      refreshRatings();
      void refreshEligibility();
      toast.success(i18n.t("reviews.published"));
    },
    onError: onEligibilityError,
  });

  const edit = useMutation({
    mutationFn: async ({ id, ...input }: ReviewInput & { id: Uuid }) =>
      (await apiClient.patch<Review>(`${BASE}${id}/`, input)).data,
    onSuccess: (review) => {
      update((reviews) => reviews.map((r) => (r.id === review.id ? review : r)));
      refreshRatings();
      toast.success(i18n.t("reviews.updated"));
    },
  });

  const remove = useMutation({
    mutationFn: async (id: Uuid) => {
      await apiClient.delete(`${BASE}${id}/`);
      return id;
    },
    onSuccess: (id) => {
      update((reviews) => reviews.filter((r) => r.id !== id));
      refreshRatings();
      void refreshEligibility();
      toast.success(i18n.t("reviews.deleted"));
    },
    onError: (error) => {
      toast.error(reviewErrorMessage(error, "delete"));
      // Un signalement a pu s'ouvrir depuis le chargement : on relit l'avis pour refléter son état
      if (apiErrorCode(error) === "review_locked") void queryClient.invalidateQueries({ queryKey: key });
    },
  });

  const reply = useMutation({
    mutationFn: async ({ id, reply_content }: { id: Uuid; reply_content: string }) =>
      (await apiClient.post<Review>(`${BASE}${id}/reply/`, { reply_content })).data,
    onSuccess: (review) => {
      update((reviews) => reviews.map((r) => (r.id === review.id ? review : r)));
      toast.success(i18n.t("reviews.replyPublished"));
    },
  });

  return { create, edit, remove, reply };
}

/** Signalement « contact fictif » d'un avis par le vendeur concerné (le serveur contrôle le rôle : 403 not_seller). */
export function useReportFakeContact() {
  return useMutation({
    mutationFn: async ({ reviewId, description }: { reviewId: Uuid; description: string }) =>
      (
        await apiClient.post("moderation/reports/", {
          target_type: "REVIEW",
          object_id: reviewId,
          reason: "CONTACT_FICTIF",
          // description facultative : n'est envoyée que si elle n'est pas vide
          ...(description.trim() ? { description: description.trim() } : {}),
        })
      ).data,
    onSuccess: () => toast.success(i18n.t("reviews.reportSent")),
  });
}

/** Réponse de l'auteur d'un avis contesté (une seule fois, tant que le signalement est ouvert). */
export function useAuthorResponse(postId: Uuid) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ reportId, author_response }: { reportId: Uuid; author_response: string }) =>
      (
        await apiClient.post<AuthorResponseResult>(`moderation/reports/${reportId}/author-response/`, {
          author_response: author_response.trim(),
        })
      ).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: reviewKeys.forPost(postId) });
      toast.success(i18n.t("reviews.contest.sent"));
    },
    onError: (error) => {
      // Déjà répondu ou signalement clos : l'état affiché n'est plus à jour
      const code = apiErrorCode(error);
      if (code === "already_responded" || code === "report_closed") {
        void queryClient.invalidateQueries({ queryKey: reviewKeys.forPost(postId) });
      }
    },
  });
}
