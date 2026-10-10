import { useInfiniteQuery, useMutation } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { Paginated, ReceivedReveal, RevealChannel, RevealedContact, Uuid } from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";

export const revealKeys = {
  received: (channel?: RevealChannel) => ["interactions", "reveals-received", channel ?? "all"] as const,
};

/**
 * Révélation du numéro du vendeur (ADR 0005 §5.4). La réponse contient le numéro : il reste dans
 * l'état de la mutation (gcTime 0, effacé par `reset()` à la fermeture) et n'est jamais écrit dans
 * le cache des requêtes, un stockage du navigateur ou un journal.
 */
export function useRevealContact() {
  return useMutation({
    mutationFn: async ({ offer, channel }: { offer: Uuid; channel: RevealChannel }) =>
      (await apiClient.post<RevealedContact>("interactions/contacts/reveal/", { offer, channel })).data,
    gcTime: 0,
    retry: false,
  });
}

/** « Qui a demandé » : demandes de numéro reçues par le vendeur, paginées, filtrables par canal (ADR 0005 §5.5). */
export function useReceivedReveals(channel?: RevealChannel) {
  const { isAuthenticated } = useAuth();
  return useInfiniteQuery({
    queryKey: revealKeys.received(channel),
    queryFn: async ({ pageParam }) =>
      (
        await apiClient.get<Paginated<ReceivedReveal>>("interactions/contacts/reveals/received/", {
          params: { ...(channel ? { channel } : {}), page: pageParam },
        })
      ).data,
    initialPageParam: 1,
    getNextPageParam: (last, _pages, lastPage) => (last.next ? lastPage + 1 : undefined),
    select: (data) => ({ reveals: data.pages.flatMap((page) => page.results), count: data.pages[0]?.count ?? 0 }),
    enabled: isAuthenticated,
    staleTime: 0,
  });
}
