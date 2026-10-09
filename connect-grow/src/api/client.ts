import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { API_URL } from "@/config/env";
import { httpStatus } from "@/lib/errors";
import { AUTH_EXPIRED_EVENT, tokenStorage } from "@/lib/tokens";

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

const refreshAccessToken = async (): Promise<RefreshResult> => {
  const refresh = tokenStorage.getRefresh();
  if (!refresh) return { kind: "expired" };
  try {
    const { data } = await axios.post(`${API_URL}accounts/token/refresh/`, { refresh });
    tokenStorage.set(data.access, data.refresh);
    return { kind: "ok", access: data.access as string };
  } catch (error) {
    // Seul un refus d'authentification clôt la session ; un 429 ou une panne ne doit ni
    // déconnecter l'utilisateur ni relancer le refresh en boucle.
    const status = httpStatus(error);
    return status === 400 || status === 401 || status === 403 ? { kind: "expired" } : { kind: "failed", error };
  }
};

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    if (error.response?.status !== 401 || !original || original._retry || isPublicAuthEndpoint(original.url) || isLogoutEndpoint(original.url)) {
      return Promise.reject(error);
    }
    original._retry = true;

    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
    const result = await refreshPromise;

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
