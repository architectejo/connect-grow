import { useQuery, type QueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { AvailableContext, ContextsData, ContextsResponse, UnavailableOrganization, Uuid } from "@/api/types";
import { shouldRetryQuery } from "@/lib/errors";

export const contextsKeys = {
  all: ["contexts"] as const,
  forUser: (userId: Uuid) => ["contexts", userId] as const,
};

/**
 * Fraîcheur de la liste des profils. Le serveur limite `contexts/` à 600 appels par heure : la liste est
 * lue une fois, puis seulement (1) après une action qui change les appartenances, (2) après un refus DENY_*
 * (règle 9.1), (3) à l'expiration de ce délai quand l'écran est rouvert. Jamais au retour de focus.
 */
export const CONTEXTS_STALE_TIME_MS = 5 * 60 * 1000;

export const CONTEXTS_URL = "accounts/contexts/";

/**
 * Normalise la réponse de `contexts/` : `status` absent vaut `ACTIVE`, `unavailable` absent vaut `[]`,
 * et seules les organisations `SUSPENDED` ou `ARCHIVED` sont gardées dans `unavailable`.
 */
export function parseContexts(data: ContextsResponse | AvailableContext[] | null | undefined): ContextsData {
  const body = Array.isArray(data) ? { results: data, unavailable: undefined } : (data ?? { results: [], unavailable: undefined });
  const results = (body.results ?? []).map((item) => ({ ...item, status: item.status ?? "ACTIVE" }));
  const unavailable = (body.unavailable ?? []).filter(
    (item): item is UnavailableOrganization => item?.type === "ORGANIZATION" && (item.status === "SUSPENDED" || item.status === "ARCHIVED"),
  );
  return { results, unavailable };
}

export async function fetchContexts(): Promise<ContextsData> {
  const { data } = await apiClient.get<ContextsResponse | AvailableContext[]>(CONTEXTS_URL);
  return parseContexts(data);
}

export const contextsQueryOptions = (userId: Uuid) => ({
  queryKey: contextsKeys.forUser(userId),
  queryFn: fetchContexts,
  staleTime: CONTEXTS_STALE_TIME_MS,
  refetchOnWindowFocus: false as const,
  retry: shouldRetryQuery,
});

/** Liste des profils du compte. Une erreur (429, 5xx, réseau) conserve les données déjà reçues. */
export function useContextsQuery(userId: Uuid | undefined) {
  return useQuery({
    ...contextsQueryOptions(userId ?? ""),
    enabled: !!userId,
  });
}

/** À appeler après une action qui change les appartenances (création, départ, archivage, rôle…). */
export function invalidateContexts(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: contextsKeys.all });
}
