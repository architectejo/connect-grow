import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient, { unwrapList } from "@/api/client";
import type { Review, Uuid } from "@/api/types";
import { apiErrorMessage } from "@/lib/errors";

export const reviewKeys = {
  forPost: (postId: Uuid) => ["reviews", "post", postId] as const,
};

export function useReviews(postId?: Uuid) {
  return useQuery({
    queryKey: reviewKeys.forPost(postId ?? ""),
    queryFn: async () => unwrapList<Review>((await apiClient.get("interactions/reviews/", { params: { post: postId } })).data),
    enabled: !!postId,
  });
}

/** Création, modification, suppression et réponse du vendeur, avec rafraîchissement de la liste. */
export function useReviewMutations(postId: Uuid) {
  const queryClient = useQueryClient();
  const key = reviewKeys.forPost(postId);
  const update = (fn: (reviews: Review[]) => Review[]) =>
    queryClient.setQueryData<Review[]>(key, (reviews) => fn(reviews ?? []));
  const onError = (error: unknown) => toast.error(apiErrorMessage(error));

  const create = useMutation({
    mutationFn: async (input: { content: string; rating: number }) =>
      (await apiClient.post<Review>("interactions/reviews/", { post: postId, ...input })).data,
    onSuccess: (review) => {
      update((reviews) => [review, ...reviews]);
      toast.success("Votre avis a été publié.");
    },
    onError,
  });

  const edit = useMutation({
    mutationFn: async ({ id, ...input }: { id: Uuid; content: string; rating: number }) =>
      (await apiClient.patch<Review>(`interactions/reviews/${id}/`, input)).data,
    onSuccess: (review) => {
      update((reviews) => reviews.map((r) => (r.id === review.id ? review : r)));
      toast.success("Avis mis à jour.");
    },
    onError,
  });

  const remove = useMutation({
    mutationFn: async (id: Uuid) => {
      await apiClient.delete(`interactions/reviews/${id}/`);
      return id;
    },
    onSuccess: (id) => {
      update((reviews) => reviews.filter((r) => r.id !== id));
      toast.success("Avis supprimé.");
    },
    onError,
  });

  const reply = useMutation({
    mutationFn: async ({ id, reply_content }: { id: Uuid; reply_content: string }) =>
      (await apiClient.post<Review>(`interactions/reviews/${id}/reply/`, { reply_content })).data,
    onSuccess: (review) => {
      update((reviews) => reviews.map((r) => (r.id === review.id ? review : r)));
      toast.success("Votre réponse a été publiée.");
    },
    onError,
  });

  return { create, edit, remove, reply };
}
