import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { MyAwaitingInvitation, NewConfirmationCode, Paginated, Uuid } from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";
import { invalidateContexts } from "@/hooks/use-contexts";
import { MY_AWAITING_INVITATIONS_KEY } from "@/hooks/use-organization-team";
import { getApiErrorCode } from "@/lib/api-errors";
import { shouldRetryQuery } from "@/lib/errors";

// Côté personne qui a accepté une invitation Administrateur (contrat L1-01 §7.4.7, spec D2 §11). Réponses `no-store`,
// service worker en réseau seul (lib/cache-rules.ts). Le code de rattachement n'est jamais dans la liste ; la réponse
// « nouveau code » le porte : mutation `gcTime: 0`, copiée dans l'état local du dialogue puis remise à zéro.

export const myAwaitingUrl = "accounts/organization-invitations/awaiting/";
export const withdrawAwaitingUrl = (invitationId: Uuid) => `accounts/organization-invitations/${invitationId}/withdraw/`;
export const confirmationCodeUrl = (invitationId: Uuid) => `accounts/organization-invitations/${invitationId}/confirmation-code/`;

/** Taille de page de la section E17 (spec D2 §11.2). */
export const MY_AWAITING_PAGE_SIZE = 10;

/** Demandes en attente de confirmation (`AWAITING_CONFIRMATION`, et `EXPIRED` depuis moins de 7 jours). */
export function useMyAwaitingInvitations() {
  const { isAuthenticated } = useAuth();
  return useInfiniteQuery({
    queryKey: MY_AWAITING_INVITATIONS_KEY,
    queryFn: async ({ pageParam }) =>
      (
        await apiClient.get<Paginated<MyAwaitingInvitation>>(myAwaitingUrl, {
          params: { page_size: MY_AWAITING_PAGE_SIZE, ...(pageParam > 1 ? { page: pageParam } : {}) },
        })
      ).data,
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
    enabled: isAuthenticated,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: shouldRetryQuery,
    select: (data) => {
      const seen = new Set<Uuid>();
      return { invitations: data.pages.flatMap((page) => page.results).filter((i) => !seen.has(i.invitation_id) && !!seen.add(i.invitation_id)) };
    },
  });
}

/** La demande n'est plus en attente : elle a peut-être été confirmée (l'organisation apparaît alors dans `contexts/`). */
function refreshAfterGone(queryClient: ReturnType<typeof useQueryClient>, error: unknown) {
  const code = getApiErrorCode(error);
  if (code === "invitation_not_found" || code === "invitation_not_awaiting_confirmation") {
    void queryClient.invalidateQueries({ queryKey: MY_AWAITING_INVITATIONS_KEY });
    void invalidateContexts(queryClient);
  }
}

/**
 * Nouveau code : l'ancien cesse de valoir. `gcTime: 0`, **aucune relance automatique** (un nouvel appel invaliderait le code affiché).
 */
export function useRegenerateConfirmationCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (invitationId: Uuid) => (await apiClient.post<NewConfirmationCode>(confirmationCodeUrl(invitationId))).data,
    gcTime: 0,
    retry: false,
    onError: (error) => refreshAfterGone(queryClient, error),
  });
}

/** Retirer sa demande (204) : `AWAITING_CONFIRMATION -> DECLINED`. */
export function useWithdrawAwaitingInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (invitationId: Uuid) => {
      await apiClient.post(withdrawAwaitingUrl(invitationId));
    },
    gcTime: 0,
    retry: false,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MY_AWAITING_INVITATIONS_KEY });
    },
    onError: (error) => refreshAfterGone(queryClient, error),
  });
}
