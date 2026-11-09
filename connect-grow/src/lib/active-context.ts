import type { AvailableContext, ContextType, OrganizationRole, OrganizationType, Uuid } from "@/api/types";
import { CANONICAL_UUID, contextHeaderValue } from "@/lib/context-header";
import { ACTIVE_CONTEXT_KEY } from "@/lib/tokens";

/**
 * Profil actif mémorisé. Volontairement minimal (D7) : de quoi afficher le bandeau tout de suite en 3G.
 * Jamais de capacités (elles viennent toujours du serveur), de photo, de contact ni de jeton.
 * Le profil personnel n'est pas mémorisé : l'absence de valeur désigne le personnel.
 */
export interface ActiveSelection {
  userId: Uuid;
  type: Exclude<ContextType, "USER">;
  id: Uuid;
  name: string;
  role: OrganizationRole | null;
  orgType: OrganizationType | null;
}

const MAX_NAME_LENGTH = 255;

function isSelection(value: unknown): value is ActiveSelection {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.userId === "string" &&
    (v.type === "PROVIDER" || v.type === "ORGANIZATION") &&
    typeof v.id === "string" &&
    CANONICAL_UUID.test(v.id) &&
    typeof v.name === "string" &&
    v.name.length <= MAX_NAME_LENGTH
  );
}

/** Ne garde que les 6 champs attendus : une valeur modifiée à la main ne peut pas y glisser autre chose. */
function sanitize(value: ActiveSelection): ActiveSelection {
  return { userId: value.userId, type: value.type, id: value.id, name: value.name, role: value.role ?? null, orgType: value.orgType ?? null };
}

function readStorage(): ActiveSelection | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CONTEXT_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (isSelection(parsed)) return sanitize(parsed);
    localStorage.removeItem(ACTIVE_CONTEXT_KEY); // valeur corrompue : on la retire
  } catch {
    /* JSON invalide ou stockage indisponible : on retire la valeur si on peut */
    try {
      localStorage.removeItem(ACTIVE_CONTEXT_KEY);
    } catch {
      /* rien à retirer */
    }
  }
  return null;
}

function writeStorage(value: ActiveSelection | null): void {
  try {
    if (value) localStorage.setItem(ACTIVE_CONTEXT_KEY, JSON.stringify(sanitize(value)));
    else localStorage.removeItem(ACTIVE_CONTEXT_KEY);
  } catch {
    /* navigation privée : le choix reste en mémoire le temps de la page */
  }
}

/** Événement émis par le client API sur un refus 403 `DENY_*` (détail : {@link ContextDeniedDetail}). */
export const CONTEXT_DENIED_EVENT = "connecte:context-denied";

export interface ContextDeniedDetail {
  code: string;
  /** La requête refusée portait X-Context (elle agissait sous un profil non personnel). */
  sentContext: boolean;
}

// --- Magasin en mémoire, lu à chaque requête par le client API (jamais de valeur périmée entre deux rendus) ---

let current: ActiveSelection | null = null;
let hydrated = false;
const listeners = new Set<() => void>();

function hydrate() {
  if (!hydrated) {
    hydrated = true;
    current = readStorage();
  }
}

export const activeContextStore = {
  /** Sélection courante (null = profil personnel). Lue dans le stockage à la première demande. */
  get(): ActiveSelection | null {
    hydrate();
    return current;
  },
  set(next: ActiveSelection | null): void {
    hydrate();
    current = next ? sanitize(next) : null;
    writeStorage(current);
    listeners.forEach((listener) => listener());
  },
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  /** Oublie tout (déconnexion, changement de compte) : mémoire et stockage. */
  reset(): void {
    activeContextStore.set(null);
  },
  /** Tests : repart d'un état neuf, relu depuis le stockage. */
  _resetForTests(): void {
    current = null;
    hydrated = false;
    listeners.clear();
  },
};

/** En-tête X-Context du profil actif, ou undefined (profil personnel). */
export function activeContextHeader(): string | undefined {
  return contextHeaderValue(activeContextStore.get());
}

export function toSelection(userId: Uuid, context: AvailableContext): ActiveSelection | null {
  if (context.type === "USER") return null;
  return { userId, type: context.type, id: context.id, name: context.name, role: context.role, orgType: context.org_type };
}

// --- Validation contre la liste du serveur ---

/**
 * Pourquoi le profil actif a été quitté. Les quatre premières valeurs sont les codes `DENY_*` du serveur ;
 * `org_suspended` et `org_archived` sont déduites de `unavailable` (le serveur confirme le statut de l'organisation).
 */
export type LostReason = "CONTEXT" | "RELATION" | "SECURITY" | "OBJECT_STATE" | "left" | "archived" | "org_suspended" | "org_archived";

export type Reconciliation =
  | { kind: "personal" }
  | { kind: "keep"; selection: ActiveSelection }
  | { kind: "lost"; lostName: string; lostId: Uuid };

/**
 * Compare le profil mémorisé à la liste fraîche de `contexts/` (le serveur fait foi) :
 * - mémorisé d'un autre compte : ignoré (l'appelant l'efface) ;
 * - absent de la liste : perdu (jamais de repli silencieux, l'appelant affiche l'alerte) ;
 * - présent : conservé, nom et rôle rafraîchis.
 */
export function reconcileSelection(selection: ActiveSelection | null, userId: Uuid, contexts: AvailableContext[]): Reconciliation {
  if (!selection) return { kind: "personal" };
  if (selection.userId !== userId) return { kind: "personal" };
  const found = contexts.find((c) => c.type === selection.type && c.id === selection.id);
  if (!found) return { kind: "lost", lostName: selection.name, lostId: selection.id };
  return { kind: "keep", selection: toSelection(userId, found) as ActiveSelection };
}

// --- Requêtes dépendantes du profil actif ---

/**
 * Clés React Query dont les données changent avec le profil actif (mes offres, corbeille, tableau de bord,
 * réglages de contact, « qui a demandé », boîte de messages). Au changement de profil elles sont annulées puis
 * réinitialisées : l'écran repasse par l'état de chargement et ne montre jamais les données de l'ancien profil.
 */
export function isContextDependentQuery(queryKey: readonly unknown[]): boolean {
  const [root, second] = queryKey;
  if (root === "account") return second === "dashboard" || second === "trash" || second === "contact-settings";
  if (root === "marketplace") return second === "my-posts";
  if (root === "messages") return true;
  if (root === "interactions") return second === "reveals-received";
  return false;
}
