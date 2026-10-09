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
  logout: () => void;
  refreshUser: () => Promise<unknown>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const ME_QUERY_KEY = ["accounts", "me"] as const;

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

  const logout = useCallback(() => {
    tokenStorage.clear();
    setHasToken(false);
    queryClient.removeQueries({ queryKey: ME_QUERY_KEY });
  }, [queryClient]);

  // Session expirée (signalée par le client API) ou connexion/déconnexion dans un autre onglet
  useEffect(() => {
    const onExpired = () => logout();
    const onStorage = (event: StorageEvent) => {
      if (event.key === "access_token") setHasToken(!!event.newValue);
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
      window.removeEventListener("storage", onStorage);
    };
  }, [logout]);

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      const { data } = await apiClient.post("accounts/login/", credentials);
      tokenStorage.set(data.access, data.refresh);
      setHasToken(true);
      const user = await queryClient.fetchQuery({ queryKey: ME_QUERY_KEY, queryFn: fetchMe });
      // Compatibilité avec les pages qui lisent encore ces clés
      try {
        localStorage.setItem("user_full_name", user.full_name);
        localStorage.setItem("user_id", String(user.id));
      } catch {
        /* stockage indisponible */
      }
      return user;
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
