import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { AvailableContext, ContextType, OrganizationRole, OrganizationType, Uuid } from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";
import { contextsQueryOptions, useContextsQuery } from "@/hooks/use-contexts";
import {
  CONTEXT_DENIED_EVENT,
  activeContextStore,
  isContextDependentQuery,
  reconcileSelection,
  toSelection,
  type ContextDeniedDetail,
  type LostReason,
} from "@/lib/active-context";
import { isContextDenyCode, lostReasonFor } from "@/lib/api-errors";

/** Durée d'affichage maximale de l'alerte « profil perdu » (D8) : fermable avant, jamais un simple toast. */
export const LOST_ALERT_MAX_MS = 30 * 60 * 1000;
/** Deux rechargements de `contexts/` provoqués par des refus de permission ne se suivent pas de plus près. */
const PERMISSION_RELOAD_MIN_INTERVAL_MS = 10_000;

/** Profil sous lequel l'utilisateur agit. `capabilities` est vide tant que le serveur ne l'a pas confirmé. */
export interface ActiveContext {
  type: ContextType;
  id: Uuid;
  name: string;
  role: OrganizationRole | null;
  orgType: OrganizationType | null;
  photo: string | null;
  capabilities: string[];
  /** Vrai quand ces informations viennent de la dernière liste du serveur (et non de la mémorisation locale). */
  confirmed: boolean;
}

export interface LostInfo {
  reason: LostReason;
  lostName: string;
}

interface ActiveContextValue {
  contexts: AvailableContext[];
  active: ActiveContext;
  /** Premier chargement de `contexts/` en cours (aucune liste reçue). */
  isLoading: boolean;
  /** Le dernier chargement a échoué (429, 5xx, réseau) : le profil actif est conservé tel quel. */
  isError: boolean;
  refetch: () => void;
  /** Change de profil (sans appel réseau). Ignoré si le profil n'est pas dans la liste du serveur. */
  setActive: (target: Pick<AvailableContext, "type" | "id">) => void;
  switchToPersonal: () => void;
  /**
   * Le compte vient de quitter ou d'archiver ce profil : s'il est actif, retour au profil personnel AVEC l'alerte
   * persistante (`left` ou `archived`), jamais un repli silencieux. Sans effet si ce n'est pas le profil actif.
   */
  leaveActive: (target: Pick<AvailableContext, "type" | "id">, reason: "left" | "archived") => void;
  lost: LostInfo | null;
  dismissLost: () => void;
}

const ActiveContextContext = createContext<ActiveContextValue | undefined>(undefined);

const isDependent = (query: { queryKey: readonly unknown[] }) => isContextDependentQuery(query.queryKey);

export function ActiveContextProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const selection = useSyncExternalStore(activeContextStore.subscribe, activeContextStore.get, () => null);
  const query = useContextsQuery(userId);
  const contexts = useMemo(() => query.data ?? [], [query.data]);
  const [lost, setLost] = useState<LostInfo | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const pendingReason = useRef<LostReason | null>(null);
  const lastPermissionReload = useRef(0);

  /** Annule les requêtes du profil quitté puis les réinitialise : écran de chargement, jamais l'ancien contenu. */
  const cancelDependentQueries = useCallback(() => queryClient.cancelQueries({ predicate: isDependent }), [queryClient]);
  const resetDependentQueries = useCallback(() => queryClient.resetQueries({ predicate: isDependent }), [queryClient]);

  const leaveSelection = useCallback(() => {
    void cancelDependentQueries();
    activeContextStore.set(null);
    void resetDependentQueries();
  }, [cancelDependentQueries, resetDependentQueries]);

  /** Valide le profil actif contre la liste fraîche du serveur, qui fait foi (règle 9.1). */
  const applyContexts = useCallback(
    (list: AvailableContext[]) => {
      if (!userId) return;
      const current = activeContextStore.get();
      const result = reconcileSelection(current, userId, list);
      if (result.kind === "keep") {
        pendingReason.current = null;
        const next = result.selection;
        if (current && (current.name !== next.name || current.role !== next.role || current.orgType !== next.orgType)) {
          activeContextStore.set(next);
        }
      } else if (result.kind === "lost") {
        const reason = pendingReason.current ?? "CONTEXT";
        pendingReason.current = null;
        leaveSelection();
        setLost({ reason, lostName: result.lostName });
      } else if (current) {
        leaveSelection(); // profil mémorisé par un autre compte du même appareil : effacé sans alerte
      }
    },
    [userId, leaveSelection],
  );

  // Validation à chaque liste reçue avec succès. Une erreur ne passe jamais par ici : le profil est conservé.
  useEffect(() => {
    if (query.isSuccess) applyContexts(query.data);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seule une nouvelle réponse du serveur déclenche la validation
  }, [query.dataUpdatedAt, query.isSuccess, userId]);

  // Compte déconnecté : le profil mémorisé n'est plus à personne.
  useEffect(() => {
    if (!isAuthenticated) {
      if (activeContextStore.get()) leaveSelection();
      setLost(null);
    }
  }, [isAuthenticated, leaveSelection]);

  // Profil mémorisé par un autre compte du même appareil : retiré dès que le compte connecté est connu
  useEffect(() => {
    const current = activeContextStore.get();
    if (userId && current && current.userId !== userId) leaveSelection();
  }, [userId, leaveSelection]);

  // Règle 9.1 : sur un refus qui peut concerner le profil, recharger `contexts/` et ne quitter le profil que s'il a disparu.
  useEffect(() => {
    if (!userId) return;
    const reload = async (reason: LostReason | null) => {
      pendingReason.current = reason;
      try {
        const list = await queryClient.fetchQuery({ ...contextsQueryOptions(userId), staleTime: 0 });
        applyContexts(list);
      } catch {
        /* 429, 5xx, réseau : on ne sait rien de nouveau, le profil actif est conservé */
      } finally {
        pendingReason.current = null;
      }
    };
    const onDenied = (event: Event) => {
      const { code, sentContext } = (event as CustomEvent<ContextDeniedDetail>).detail;
      if (code === "DENY_PERMISSION") {
        // Le rôle a peut-être changé : réaligner les boutons, sans jamais quitter le profil pour cela
        const now = Date.now();
        if (now - lastPermissionReload.current < PERMISSION_RELOAD_MIN_INTERVAL_MS) return;
        lastPermissionReload.current = now;
        void reload(null);
      } else if (sentContext && isContextDenyCode(code)) {
        void reload(lostReasonFor(code));
      }
    };
    window.addEventListener(CONTEXT_DENIED_EVENT, onDenied);
    return () => window.removeEventListener(CONTEXT_DENIED_EVENT, onDenied);
  }, [userId, queryClient, applyContexts]);

  // L'alerte reste jusqu'à fermeture, ou 30 minutes.
  useEffect(() => {
    if (!lost) return;
    const timer = window.setTimeout(() => setLost(null), LOST_ALERT_MAX_MS);
    return () => window.clearTimeout(timer);
  }, [lost]);

  const active = useMemo<ActiveContext>(() => {
    const own = selection && (!userId || selection.userId === userId) ? selection : null;
    const fromServer = own ? contexts.find((c) => c.type === own.type && c.id === own.id) : contexts.find((c) => c.type === "USER");
    if (fromServer) {
      return {
        type: fromServer.type,
        id: fromServer.id,
        name: fromServer.name,
        role: fromServer.role,
        orgType: fromServer.org_type,
        photo: fromServer.photo,
        capabilities: fromServer.capabilities,
        confirmed: true,
      };
    }
    if (own) {
      // Nom mémorisé : affiché tout de suite en 3G ; aucune capacité tant que le serveur ne répond pas
      return { type: own.type, id: own.id, name: own.name, role: own.role, orgType: own.orgType, photo: null, capabilities: [], confirmed: false };
    }
    return { type: "USER", id: userId ?? "", name: user?.full_name ?? "", role: null, orgType: null, photo: null, capabilities: [], confirmed: false };
  }, [selection, contexts, userId, user?.full_name]);

  const setActive = useCallback(
    (target: Pick<AvailableContext, "type" | "id">) => {
      if (!userId) return;
      const found = contexts.find((c) => c.type === target.type && c.id === target.id);
      if (!found) return;
      const current = activeContextStore.get();
      const already = found.type === "USER" ? !current : current?.type === found.type && current.id === found.id;
      if (already) return;
      void cancelDependentQueries();
      activeContextStore.set(toSelection(userId, found));
      void resetDependentQueries();
      setAnnouncement(t("context.switched", { name: found.name }));
    },
    [userId, contexts, cancelDependentQueries, resetDependentQueries, t],
  );

  const switchToPersonal = useCallback(() => {
    const personal = contexts.find((c) => c.type === "USER");
    if (personal) setActive(personal);
    else if (activeContextStore.get()) leaveSelection();
  }, [contexts, setActive, leaveSelection]);

  const leaveActive = useCallback(
    (target: Pick<AvailableContext, "type" | "id">, reason: "left" | "archived") => {
      const current = activeContextStore.get();
      if (!current || current.type !== target.type || current.id !== target.id) return;
      const lostName = current.name;
      leaveSelection();
      setLost({ reason, lostName });
    },
    [leaveSelection],
  );

  const value = useMemo<ActiveContextValue>(
    () => ({
      contexts,
      active,
      isLoading: !!userId && query.isPending,
      isError: query.isError,
      refetch: () => void query.refetch(),
      setActive,
      switchToPersonal,
      leaveActive,
      lost,
      dismissLost: () => setLost(null),
    }),
    [contexts, active, userId, query, setActive, switchToPersonal, leaveActive, lost],
  );

  return (
    <ActiveContextContext.Provider value={value}>
      {children}
      {/* Annonce vocale du changement de profil ; montée une seule fois */}
      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>
    </ActiveContextContext.Provider>
  );
}

export function useActiveContext(): ActiveContextValue {
  const value = useContext(ActiveContextContext);
  if (!value) throw new Error("useActiveContext doit être utilisé dans un ActiveContextProvider");
  return value;
}

/** Profil actif si un fournisseur est monté, sinon undefined (composants affichables hors du fournisseur, comme les rappels). */
export function useOptionalActiveContext(): ActiveContextValue | undefined {
  return useContext(ActiveContextContext);
}

/**
 * Le profil actif a-t-il cette capacité ? Réponse du serveur (`capabilities` de `contexts/`), jamais un rôle codé en dur.
 * Faux tant que le serveur n'a pas confirmé le profil. Le masquage n'est pas le contrôle : le serveur refuse de toute façon.
 */
export function useCan(capability: string): boolean {
  return useActiveContext().active.capabilities.includes(capability);
}
