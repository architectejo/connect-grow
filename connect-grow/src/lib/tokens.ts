const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

/** Événement émis quand la session expire et ne peut pas être rafraîchie. */
export const AUTH_EXPIRED_EVENT = "connecte:auth-expired";

/** Clé du brouillon d'annonce (PostEditor) : données de l'utilisateur, purgées à la déconnexion. */
export const POST_DRAFT_KEY = "connecte:post-draft";

/** Cache PWA des contenus d'annonces : purgé à la déconnexion pour ne rien laisser d'une session précédente. */
export const API_CONTENT_CACHE = "api-annonces-v2";

/** Ancien cache des annonces (réponses contenant le téléphone des vendeurs) : purgé aussi, jamais réutilisé. */
const LEGACY_API_CONTENT_CACHE = "api-annonces";

/** Caches applicatifs pouvant contenir des données de la session (voir vite.config.ts) : tous purgés à la déconnexion. */
export const SESSION_CACHES = [API_CONTENT_CACHE, LEGACY_API_CONTENT_CACHE, "api-referentiels", "photos"] as const;

const purgeApiCaches = () => {
  try {
    if (typeof caches !== "undefined") SESSION_CACHES.forEach((name) => void caches.delete(name).catch(() => undefined));
  } catch {
    /* Cache API indisponible */
  }
};

const safeGet = (key: string) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

export const tokenStorage = {
  getAccess: () => safeGet(ACCESS_KEY),
  getRefresh: () => safeGet(REFRESH_KEY),
  set(access: string, refresh?: string) {
    try {
      localStorage.setItem(ACCESS_KEY, access);
      if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    } catch {
      /* stockage indisponible (navigation privée) : la session reste en mémoire le temps de la page */
    }
  },
  clear() {
    try {
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
      // Anciennes clés (héritage, plus écrites) : à retirer après quelques versions
      localStorage.removeItem("user_full_name");
      localStorage.removeItem("user_id");
      localStorage.removeItem(POST_DRAFT_KEY);
    } catch {
      /* rien à nettoyer */
    }
    purgeApiCaches();
  },
};
