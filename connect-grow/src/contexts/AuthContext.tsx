import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { User } from "@/api/types";
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
  logout: (options?: { all?: boolean }) => void;
  refreshUser: () => Promise<unknown>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const ME_QUERY_KEY = ["accounts", "me"] as const;

/**
 * Appelle `accounts/logout/` (ou `logout-all/`) avec le refresh token. Les jetons sont lus avant la
 * purge locale et l'en-tête est fixé ici, car la purge a lieu tout de suite après. Toute erreur est ignorée.
 */
async function requestServerLogout(all = false): Promise<void> {
  const access = tokenStorage.getAccess();
  const refresh = tokenStorage.getRefresh();
  if (!access) return;
  try {
    await apiClient.post(all ? "accounts/logout-all/" : "accounts/logout/", { refresh }, { headers: { Authorization: `Bearer ${access}` } });
  } catch {
    /* session déjà invalide, 429 ou réseau coupé : la déconnexion locale suffit */
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
    setHasToken(false);
    // Vide tout le cache en mémoire : aucune donnée privée ne survit à la session
    queryClient.clear();
  }, [queryClient]);

  // Déconnexion voulue : le serveur révoque d'abord le refresh token, puis on purge sans l'attendre
  // (réseau faible, ou serveur injoignable : l'utilisateur est déconnecté ici dans tous les cas).
  const logout = useCallback(
    (options?: { all?: boolean }) => {
      void requestServerLogout(options?.all);
      clearSession();
    },
    [clearSession],
  );

  // Session expirée (signalée par le client API) ou connexion/déconnexion dans un autre onglet
  useEffect(() => {
    const onExpired = () => clearSession();
    const onStorage = (event: StorageEvent) => {
      if (event.key === "access_token") setHasToken(!!event.newValue);
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
      refreshUser: refetch,
    }),
    [user, hasToken, isPending, login, logout, refetch],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans un AuthProvider");
  return context;
}
