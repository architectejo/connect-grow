import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { API_URL } from "@/config/env";
import { httpStatus, retryAfterSeconds } from "@/lib/errors";
import { AUTH_EXPIRED_EVENT, tokenStorage } from "@/lib/tokens";
import { CONTEXT_DENIED_EVENT, activeContextHeader, type ContextDeniedDetail } from "@/lib/active-context";
import { CONTEXT_HEADER, isContextScopedRequest } from "@/lib/context-header";
import { apiErrorCode } from "@/lib/errors";

// Endpoints qui ne doivent jamais recevoir de jeton : un jeton expiré y provoquerait un 401.
const PUBLIC_AUTH_ENDPOINTS = ["accounts/login/", "accounts/register/", "accounts/token/refresh/"];
const isPublicAuthEndpoint = (url?: string) => !!url && PUBLIC_AUTH_ENDPOINTS.some((path) => url.includes(path));
// La déconnexion ne déclenche jamais de rafraîchissement : un 401 y signifie « déjà déconnecté ».
const isLogoutEndpoint = (url?: string) => !!url && /accounts\/logout(-all)?\//.test(url);

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Ajoute le jeton JWT à chaque requête
apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccess();
  if (token && !isPublicAuthEndpoint(config.url)) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Profil actif (ADR 0006 §6.4) : l'en-tête n'accompagne que les appels « de mon profil » de la liste blanche,
  // et seulement hors profil personnel. Jamais pour contact, avis, favoris, signalement : ils sont toujours personnels.
  const contextHeader = activeContextHeader();
  if (contextHeader && token && isContextScopedRequest(config.method, config.url, config.params)) {
    config.headers[CONTEXT_HEADER] = contextHeader;
  }
  // Avec l'en-tête JSON par défaut, axios convertirait un FormData en JSON (photos perdues).
  // En multipart, le navigateur ajoute lui-même la délimitation (boundary).
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    config.headers["Content-Type"] = "multipart/form-data";
  }
  return config;
});

// Rafraîchissement du jeton d'accès (15 min) : une seule requête de refresh partagée
type RefreshResult =
  | { kind: "ok"; access: string }
  | { kind: "expired" } // refresh refusé ou absent : la session est terminée
  | { kind: "failed"; error: unknown }; // 429, 5xx, réseau : la session reste ouverte, on ne relance pas

let refreshPromise: Promise<RefreshResult> | null = null;

// Après un 429 sur le refresh, aucune nouvelle tentative avant l'échéance (Retry-After) : les requêtes
// qui arrivent entre-temps échouent tout de suite avec la même erreur 429, sans solliciter le serveur.
const DEFAULT_REFRESH_BLOCK_SECONDS = 30;
let refreshBlock: { until: number; error: unknown } | null = null;

/** Réinitialise l'état du rafraîchissement (tests, changement de session). */
export function resetRefreshState(): void {
  refreshPromise = null;
  refreshBlock = null;
}

const refreshAccessToken = async (): Promise<RefreshResult> => {
  const refresh = tokenStorage.getRefresh();
  if (!refresh) return { kind: "expired" };
  if (refreshBlock && Date.now() < refreshBlock.until) return { kind: "failed", error: refreshBlock.error };
  try {
    const { data } = await axios.post(`${API_URL}accounts/token/refresh/`, { refresh });
    tokenStorage.set(data.access, data.refresh);
    return { kind: "ok", access: data.access as string };
  } catch (error) {
    // Seul un refus d'authentification clôt la session ; un 429 ou une panne ne doit ni
    // déconnecter l'utilisateur ni relancer le refresh en boucle.
    const status = httpStatus(error);
    if (status === 429) {
      refreshBlock = { until: Date.now() + (retryAfterSeconds(error) ?? DEFAULT_REFRESH_BLOCK_SECONDS) * 1000, error };
    }
    return status === 400 || status === 401 || status === 403 ? { kind: "expired" } : { kind: "failed", error };
  }
};

/** Une seule requête de refresh à la fois, partagée par tous les appelants. */
function sharedRefresh(): Promise<RefreshResult> {
  refreshPromise ??= refreshAccessToken().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

/** Tente un rafraîchissement du jeton d'accès ; renvoie le nouveau jeton, ou null si impossible. */
export async function refreshSession(): Promise<string | null> {
  const result = await sharedRefresh();
  return result.kind === "ok" ? result.access : null;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    // Refus d'autorisation : le fournisseur du profil actif décide s'il faut recharger `contexts/` (règle 9.1).
    const denyCode = error.response?.status === 403 ? apiErrorCode(error) : undefined;
    if (denyCode?.startsWith("DENY_") && typeof window !== "undefined") {
      const detail: ContextDeniedDetail = { code: denyCode, sentContext: !!original?.headers?.[CONTEXT_HEADER] };
      window.dispatchEvent(new CustomEvent<ContextDeniedDetail>(CONTEXT_DENIED_EVENT, { detail }));
    }
    if (error.response?.status !== 401 || !original || original._retry || isPublicAuthEndpoint(original.url) || isLogoutEndpoint(original.url)) {
      return Promise.reject(error);
    }
    original._retry = true;

    const result = await sharedRefresh();

    if (result.kind === "failed") return Promise.reject(result.error);

    if (result.kind === "ok") {
      original.headers.Authorization = `Bearer ${result.access}`;
    } else {
      // Session expirée : on la ferme, puis on rejoue la requête en anonyme
      // (les contenus publics restent accessibles, les privés renverront 401).
      tokenStorage.clear();
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      delete original.headers.Authorization;
    }
    return apiClient(original);
  },
);

/** Normalise une réponse de liste DRF, paginée ({ results }) ou non (tableau). */
export function unwrapList<T>(data: T[] | { results?: T[] } | null | undefined): T[] {
  if (Array.isArray(data)) return data;
  return data?.results ?? [];
}

export default apiClient;
