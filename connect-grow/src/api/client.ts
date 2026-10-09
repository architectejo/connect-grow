import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { API_URL } from "@/config/env";
import { AUTH_EXPIRED_EVENT, tokenStorage } from "@/lib/tokens";

// Endpoints qui ne doivent jamais recevoir de jeton : un jeton expiré y provoquerait un 401.
const PUBLIC_AUTH_ENDPOINTS = ["accounts/login/", "accounts/register/", "accounts/token/refresh/"];
const isPublicAuthEndpoint = (url?: string) => !!url && PUBLIC_AUTH_ENDPOINTS.some((path) => url.includes(path));

const apiClient = axios.create({
  baseURL: API_URL,
  withCredentials: true,
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
let refreshPromise: Promise<string | null> | null = null;

const refreshAccessToken = async (): Promise<string | null> => {
  const refresh = tokenStorage.getRefresh();
  if (!refresh) return null;
  try {
    const { data } = await axios.post(`${API_URL}accounts/token/refresh/`, { refresh });
    tokenStorage.set(data.access, data.refresh);
    return data.access as string;
  } catch {
    return null;
  }
};

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    if (error.response?.status !== 401 || !original || original._retry || isPublicAuthEndpoint(original.url)) {
      return Promise.reject(error);
    }
    original._retry = true;

    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
    const access = await refreshPromise;

    if (access) {
      original.headers.Authorization = `Bearer ${access}`;
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
