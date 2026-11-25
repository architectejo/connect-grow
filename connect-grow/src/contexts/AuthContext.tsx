import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient, { refreshSession } from "@/api/client";
import i18n from "@/i18n";
import { httpStatus } from "@/lib/errors";
import type { User } from "@/api/types";
import { clearInvitationToken } from "@/lib/invitation-token";
import { clearLegacyNotices } from "@/lib/legacy-notice";
import { AUTH_EXPIRED_EVENT, tokenStorage } from "@/lib/tokens";

/** Connexion par e-mail OU par téléphone au format +243XXXXXXXXX (CDC 3.1). */
export type LoginCredentials = { password: string } & ({ email: string; phone?: never } | { phone: string; email?: never });

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  /** Vrai tant que le profil d'un utilisateur connecté n'est pas chargé. */
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<User>;
  /** Ferme la session ici et révoque le refresh token côté serveur (`all` : tous les appareils). */
  logout: (options?: { all?: boolean }) => Promise<void>;
  /** Purge locale seule (sans appel serveur) : session déjà révoquée ou expirée. */
  endSession: () => void;
  refreshUser: () => Promise<unknown>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const ME_QUERY_KEY = ["accounts", "me"] as const;

const authHeader = (access: string | null) => (access ? { headers: { Authorization: `Bearer ${access}` } } : undefined);

/**
 * Révoque la session côté serveur. Les jetons sont lus avant la purge locale et l'en-tête est fixé ici.
 * - `logout/` n'a besoin que du refresh token : toute erreur est ignorée (la purge locale suffit).
 * - `logout-all/` exige un accès valide : sur 401, UN rafraîchissement puis UN rejeu. Renvoie false
 *   si les autres appareils n'ont pas pu être déconnectés, pour que l'appelant le dise à l'utilisateur.
 */
async function requestServerLogout(all = false): Promise<boolean> {
  const access = tokenStorage.getAccess();
  const refresh = tokenStorage.getRefresh();
  if (!all) {
    if (!refresh) return true;
    try {
      await apiClient.post("accounts/logout/", { refresh }, authHeader(access));
    } catch {
      /* session déjà invalide, 429 ou réseau coupé : la déconnexion locale suffit */
    }
    return true;
  }

  const send = (token: string) => apiClient.post("accounts/logout-all/", { refresh: tokenStorage.getRefresh() ?? refresh }, authHeader(token));
  try {
    await send(access ?? (await refreshSession()) ?? "");
    return true;
  } catch (error) {
    if (httpStatus(error) !== 401) return false;
  }
  try {
    const fresh = await refreshSession();
    if (!fresh) return false;
    await send(fresh);
    return true;
  } catch {
    return false;
  }
}

const fetchMe = async () => (await apiClient.get<User>("accounts/me/")).data;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(() => !!tokenStorage.getAccess());

  const meQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMe,
    enabled: hasToken,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  // Purge locale : jetons, brouillon, caches. Sans appel serveur (session déjà expirée ou fermée ailleurs).
  const clearSession = useCallback(() => {
    tokenStorage.clear();
    clearLegacyNotices();
    // Jeton d'invitation rangé dans l'onglet : jamais réutilisable par le compte suivant (L1-01-F2, audit S2).
    // Couvre la déconnexion, la session expirée et la déconnexion depuis un autre onglet.
    clearInvitationToken();
    setHasToken(false);
    // Vide tout le cache en mémoire : aucune donnée privée ne survit à la session
    queryClient.clear();
  }, [queryClient]);

  // Déconnexion voulue : le serveur révoque d'abord le refresh token, puis on purge sans l'attendre
  // (réseau faible, ou serveur injoignable : l'utilisateur est déconnecté ici dans tous les cas).
  const logout = useCallback(
    async (options?: { all?: boolean }) => {
      if (options?.all) {
        const done = await requestServerLogout(true);
        clearSession();
        if (!done) toast.error(i18n.t("auth.logoutAllFailed"));
        return;
      }
      void requestServerLogout(false);
      clearSession();
    },
    [clearSession],
  );

  // Session expirée (signalée par le client API) ou connexion/déconnexion dans un autre onglet
  useEffect(() => {
    const onExpired = () => clearSession();
    const onStorage = (event: StorageEvent) => {
      // Jeton retiré dans un autre onglet (déconnexion) : même purge complète qu'ici (cache mémoire, brouillon, caches PWA)
      if (event.key === "access_token" || event.key === null) {
        if (tokenStorage.getAccess()) setHasToken(true);
        else clearSession();
      }
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
      window.removeEventListener("storage", onStorage);
    };
  }, [clearSession]);

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      const { data } = await apiClient.post("accounts/login/", credentials);
      tokenStorage.set(data.access, data.refresh);
      setHasToken(true);
      return queryClient.fetchQuery({ queryKey: ME_QUERY_KEY, queryFn: fetchMe });
    },
    [queryClient],
  );

  const { data: user, isPending, refetch } = meQuery;

  const value = useMemo<AuthContextValue>(
    () => ({
      user: user ?? null,
      isAuthenticated: hasToken,
      isLoading: hasToken && isPending,
      login,
      logout,
      endSession: clearSession,
      refreshUser: refetch,
    }),
    [user, hasToken, isPending, login, logout, clearSession, refetch],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans un AuthProvider");
  return context;
}
