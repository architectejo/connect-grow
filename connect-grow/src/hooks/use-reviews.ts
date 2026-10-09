import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient, { unwrapList } from "@/api/client";
import type { Review } from "@/api/types";

export const reviewKeys = {
  forPost: (postId: string | number) => ["reviews", "post", String(postId)] as const,
};

/** Premier message d'erreur lisible d'une réponse DRF. */
export function apiErrorMessage(error: unknown, fallback = "Une erreur est survenue."): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (!data || typeof data !== "object") return fallback;
  const record = data as Record<string, unknown>;
  const first = record.non_field_errors ?? record.detail ?? record.error ?? Object.values(record)[0];
  if (Array.isArray(first)) return String(first[0]);
  return typeof first === "string" ? first : fallback;
}

export function useReviews(postId?: string | number) {
  return useQuery({
    queryKey: reviewKeys.forPost(postId ?? ""),
    queryFn: async () => unwrapList<Review>((await apiClient.get("interactions/reviews/", { params: { post: postId } })).data),
    enabled: !!postId,
  });
}

/** Création, modification, suppression et réponse du vendeur, avec rafraîchissement de la liste. */
export function useReviewMutations(postId: string | number) {
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
    mutationFn: async ({ id, ...input }: { id: number; content: string; rating: number }) =>
      (await apiClient.patch<Review>(`interactions/reviews/${id}/`, input)).data,
    onSuccess: (review) => {
      update((reviews) => reviews.map((r) => (r.id === review.id ? review : r)));
      toast.success("Avis mis à jour.");
    },
    onError,
  });

  const remove = useMutation({
    mutationFn: async (id: number) => {
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
    mutationFn: async ({ id, reply_content }: { id: number; reply_content: string }) =>
      (await apiClient.post<Review>(`interactions/reviews/${id}/reply/`, { reply_content })).data,
    onSuccess: (review) => {
      update((reviews) => reviews.map((r) => (r.id === review.id ? review : r)));
      toast.success("Votre réponse a été publiée.");
    },
    onError,
  });

  return { create, edit, remove, reply };
}
