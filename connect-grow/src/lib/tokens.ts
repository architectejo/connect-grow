const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

/** Événement émis quand la session expire et ne peut pas être rafraîchie. */
export const AUTH_EXPIRED_EVENT = "connecte:auth-expired";

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
      localStorage.removeItem("user_full_name");
      localStorage.removeItem("user_id");
    } catch {
      /* rien à nettoyer */
    }
  },
};
