import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosResponse } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import fixture from "@/api/__fixtures__/contexts.json";
import type { AvailableContext } from "@/api/types";
import { CONTEXTS_STALE_TIME_MS, CONTEXTS_URL } from "@/hooks/use-contexts";
import { CONTEXT_DENIED_EVENT, activeContextStore, toSelection } from "@/lib/active-context";
import { ACTIVE_CONTEXT_KEY } from "@/lib/tokens";
import { ActiveContextProvider, LOST_ALERT_MAX_MS, useActiveContext, useCan } from "./ActiveContextContext";

const auth = { user: { id: "11111111-1111-4111-8111-111111111111", full_name: "Compte Test" } as { id: string; full_name: string } | null, isAuthenticated: true };
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

const all = fixture.response.results as AvailableContext[];
const [personal, provider, shop, collective] = all;
const USER_ID = personal.id;

let server: AvailableContext[];
let serverUnavailable: unknown[] | undefined;
let failWith: { status?: number } | null;
let calls: number;
let queryClient: QueryClient;

const failure = (status?: number) =>
  status === undefined
    ? new AxiosError("Network Error")
    : new AxiosError(`HTTP ${status}`, String(status), undefined, null, { status, data: { detail: "x" }, headers: {} } as unknown as AxiosResponse);

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <ActiveContextProvider>{children}</ActiveContextProvider>
  </QueryClientProvider>
);

const setup = () => renderHook(() => ({ ctx: useActiveContext(), canPublish: useCan("offer.publish"), canLeave: useCan("org.leave") }), { wrapper });
const settle = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 40)));
const deny = (code: string, sentContext = true) => act(() => void window.dispatchEvent(new CustomEvent(CONTEXT_DENIED_EVENT, { detail: { code, sentContext } })));

beforeEach(() => {
  localStorage.clear();
  activeContextStore._resetForTests();
  auth.user = { id: USER_ID, full_name: "Compte Test" };
  auth.isAuthenticated = true;
  server = all;
  serverUnavailable = undefined;
  failWith = null;
  calls = 0;
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url !== CONTEXTS_URL) return { data: {} };
    calls++;
    if (failWith) throw failure(failWith.status);
    return { data: { count: server.length, next: null, previous: null, results: server, ...(serverUnavailable ? { unavailable: serverUnavailable } : {}) } };
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("chargement et capacités", () => {
  it("profil personnel par défaut : capacités du serveur, aucun rôle codé en dur", async () => {
    const { result } = setup();
    expect(result.current.ctx.isLoading).toBe(true);
    expect(result.current.canPublish).toBe(false); // inconnu tant que le serveur n'a pas répondu
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    expect(result.current.ctx.active).toMatchObject({ type: "USER", name: "Compte Test" });
    expect(result.current.canPublish).toBe(true);
    expect(result.current.canLeave).toBe(false); // aucune capacité org.* hors organisation
    expect(result.current.ctx.contexts).toHaveLength(4);
    expect(calls).toBe(1);
  });

  it("useCan suit les capacités du profil actif, pas son rôle", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    act(() => result.current.ctx.setActive(collective)); // analyste
    expect(result.current.ctx.active.role).toBe("ANALYST");
    expect(result.current.canPublish).toBe(false);
    expect(result.current.canLeave).toBe(true);
    // Si le serveur donnait demain une capacité de plus à ce profil, le front la suivrait sans modification
    server = all.map((c) => (c.id === collective.id ? { ...c, capabilities: [...c.capabilities, "offer.publish"] } : c));
    deny("DENY_PERMISSION");
    await waitFor(() => expect(result.current.canPublish).toBe(true));
  });

  it("n'interroge contexts/ qu'une fois : ni au retour de focus, ni pour un second consommateur", async () => {
    expect(CONTEXTS_STALE_TIME_MS).toBeGreaterThanOrEqual(5 * 60 * 1000);
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    act(() => {
      window.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("visibilitychange"));
    });
    renderHook(() => useActiveContext(), { wrapper });
    await settle();
    expect(calls).toBe(1);
  });

  it("anonyme : aucun appel à contexts/", async () => {
    auth.user = null;
    auth.isAuthenticated = false;
    setup();
    await settle();
    expect(calls).toBe(0);
  });
});

describe("changement de profil", () => {
  it("mémorise le choix, annonce le changement, ne fait aucun appel réseau", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    act(() => result.current.ctx.setActive(shop));
    expect(result.current.ctx.active).toMatchObject({ type: "ORGANIZATION", id: shop.id, role: "ADMIN" });
    expect(JSON.parse(localStorage.getItem(ACTIVE_CONTEXT_KEY) as string)).toMatchObject({ userId: USER_ID, id: shop.id });
    expect(calls).toBe(1);
    expect(document.querySelector('[role="status"]')?.textContent).toContain("Boutique Test");
    act(() => result.current.ctx.switchToPersonal());
    expect(result.current.ctx.active.type).toBe("USER");
    expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).toBeNull();
  });

  it("ignore un profil qui n'est pas dans la liste du serveur", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    act(() => result.current.ctx.setActive({ type: "ORGANIZATION", id: "99999999-9999-4999-8999-999999999999" }));
    expect(result.current.ctx.active.type).toBe("USER");
  });

  it("réinitialise les requêtes du profil (jamais l'ancien contenu) et laisse les autres", async () => {
    let dashboardCalls = 0;
    let favoritesCalls = 0;
    const { result } = renderHook(
      () => {
        const ctx = useActiveContext();
        const dashboard = useQuery({ queryKey: ["account", "dashboard"], queryFn: async () => ({ n: ++dashboardCalls, as: activeContextStore.get()?.id ?? "personal" }), staleTime: Infinity });
        const favorites = useQuery({ queryKey: ["account", "favorites"], queryFn: async () => ++favoritesCalls, staleTime: Infinity });
        return { ctx, dashboard, favorites };
      },
      { wrapper },
    );
    await waitFor(() => expect(result.current.dashboard.data).toEqual({ n: 1, as: "personal" }));
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));

    act(() => result.current.ctx.setActive(shop));

    await waitFor(() => expect(result.current.dashboard.data).toEqual({ n: 2, as: shop.id }));
    expect(result.current.favorites.data).toBe(1);
    expect(favoritesCalls).toBe(1);
  });
});

describe("profil mémorisé", () => {
  const remember = (context: AvailableContext, userId = USER_ID) => activeContextStore.set(toSelection(userId, context));

  it("présent dans la liste : conservé, affiché tout de suite avec son nom mémorisé, sans capacité avant confirmation", async () => {
    remember(shop);
    const { result } = setup();
    expect(result.current.ctx.active).toMatchObject({ name: "Boutique Test", confirmed: false, capabilities: [] });
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    expect(result.current.ctx.active.id).toBe(shop.id);
    expect(result.current.ctx.lost).toBeNull();
  });

  it("absent de la liste : retour au personnel AVEC alerte persistante (jamais silencieux)", async () => {
    remember(shop);
    server = all.filter((c) => c.id !== shop.id);
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.lost).not.toBeNull());
    expect(result.current.ctx.lost).toEqual({ reason: "CONTEXT", lostName: "Boutique Test", lostId: shop.id });
    expect(result.current.ctx.active.type).toBe("USER");
    expect(activeContextStore.get()).toBeNull();
    expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).toBeNull();
    act(() => result.current.ctx.dismissLost());
    expect(result.current.ctx.lost).toBeNull();
  });

  it("absent de results mais présent dans unavailable (SUSPENDED) : alerte spécifique avec l'identifiant", async () => {
    remember(shop);
    server = all.filter((c) => c.id !== shop.id);
    serverUnavailable = [{ ...shop, status: "SUSPENDED", capabilities: ["org.leave"] }];
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.lost).not.toBeNull());
    expect(result.current.ctx.lost).toEqual({ reason: "org_suspended", lostName: "Boutique Test", lostId: shop.id });
    expect(result.current.ctx.active.type).toBe("USER");
    expect(result.current.ctx.unavailable.map((org) => org.id)).toEqual([shop.id]);
  });

  it("présent dans unavailable (ARCHIVED), refus DENY_OBJECT_STATE : alerte « archivée »", async () => {
    remember(shop);
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    server = all.filter((c) => c.id !== shop.id);
    serverUnavailable = [{ ...shop, status: "ARCHIVED", capabilities: ["org.leave"] }];
    deny("DENY_OBJECT_STATE");
    await waitFor(() => expect(result.current.ctx.lost?.reason).toBe("org_archived"));
  });

  it("DENY_SECURITY sans entrée dans unavailable (compte limité) : texte générique, jamais « suspendue »", async () => {
    remember(shop);
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    server = all.filter((c) => c.id !== shop.id);
    deny("DENY_SECURITY");
    await waitFor(() => expect(result.current.ctx.lost?.reason).toBe("SECURITY"));
  });

  it("unavailable absent : liste vide, status absent traité comme ACTIVE", async () => {
    server = all.map(({ status: _status, ...rest }) => rest as unknown as AvailableContext);
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.contexts.length).toBeGreaterThan(0));
    expect(result.current.ctx.unavailable).toEqual([]);
    expect(result.current.ctx.contexts.every((c) => c.status === "ACTIVE")).toBe(true);
  });

  it("l'alerte s'efface seule après 30 minutes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    remember(shop);
    server = all.filter((c) => c.id !== shop.id);
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.lost).not.toBeNull());
    act(() => void vi.advanceTimersByTime(LOST_ALERT_MAX_MS - 1000));
    expect(result.current.ctx.lost).not.toBeNull();
    act(() => void vi.advanceTimersByTime(1000));
    expect(result.current.ctx.lost).toBeNull();
  });

  it("mémorisé par un autre compte : effacé sans alerte", async () => {
    remember(shop, "autre-compte");
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    expect(activeContextStore.get()).toBeNull();
    expect(result.current.ctx.lost).toBeNull();
    expect(result.current.ctx.active.type).toBe("USER");
  });

  it("déconnexion : le profil mémorisé est oublié", async () => {
    remember(shop);
    const { result, rerender } = setup();
    await waitFor(() => expect(result.current.ctx.active.confirmed).toBe(true));
    auth.user = null;
    auth.isAuthenticated = false;
    rerender();
    await waitFor(() => expect(activeContextStore.get()).toBeNull());
    expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).toBeNull();
  });
});

describe("erreurs de contexts/ : le profil actif n'est jamais retiré", () => {
  it.each([
    ["429", 429],
    ["5xx", 503],
    ["réseau coupé", undefined],
  ])("%s au chargement", async (_name, status) => {
    activeContextStore.set(toSelection(USER_ID, shop));
    failWith = { status };
    server = all.filter((c) => c.id !== shop.id); // même si le serveur répondrait autre chose plus tard
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.isError).toBe(true), { timeout: 4000 });
    expect(result.current.ctx.lost).toBeNull();
    expect(result.current.ctx.active).toMatchObject({ type: "ORGANIZATION", id: shop.id, name: "Boutique Test" });
    expect(activeContextStore.get()?.id).toBe(shop.id);
    expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).not.toBeNull();
  }, 10_000);

  it("Réessayer recharge la liste et lève l'erreur", async () => {
    failWith = { status: 429 };
    const { result } = setup();
    await waitFor(() => expect(result.current.ctx.isError).toBe(true));
    failWith = null;
    act(() => result.current.ctx.refetch());
    await waitFor(() => expect(result.current.ctx.isError).toBe(false));
    expect(result.current.ctx.contexts).toHaveLength(4);
  });
});

describe("règle 9.1 : refus DENY_* sur une requête portant X-Context", () => {
  const start = async () => {
    activeContextStore.set(toSelection(USER_ID, shop));
    const hook = setup();
    await waitFor(() => expect(hook.result.current.ctx.active.confirmed).toBe(true));
    calls = 0;
    return hook;
  };

  it.each([
    ["DENY_CONTEXT", "CONTEXT"],
    ["DENY_RELATION", "RELATION"],
    ["DENY_SECURITY", "SECURITY"],
    ["DENY_OBJECT_STATE", "OBJECT_STATE"],
  ])("%s : recharge contexts/, quitte le profil s'il a disparu, avec la raison %s", async (code, reason) => {
    const { result } = await start();
    server = all.filter((c) => c.id !== shop.id);
    deny(code);
    await waitFor(() => expect(result.current.ctx.lost).toEqual({ reason, lostName: "Boutique Test", lostId: shop.id }));
    expect(calls).toBe(1);
    expect(result.current.ctx.active.type).toBe("USER");
    expect(activeContextStore.get()).toBeNull();
  });

  it("le profil figure encore dans la liste : refus local, aucun changement de profil", async () => {
    const { result } = await start();
    deny("DENY_OBJECT_STATE");
    await waitFor(() => expect(calls).toBe(1));
    await settle();
    expect(result.current.ctx.lost).toBeNull();
    expect(result.current.ctx.active.id).toBe(shop.id);
  });

  it("rechargement impossible (429 / 5xx / réseau) : le profil est conservé", async () => {
    const { result } = await start();
    failWith = { status: 429 };
    server = all.filter((c) => c.id !== shop.id);
    deny("DENY_RELATION");
    await waitFor(() => expect(calls).toBe(1));
    await settle();
    expect(result.current.ctx.lost).toBeNull();
    expect(result.current.ctx.active.id).toBe(shop.id);
    expect(activeContextStore.get()?.id).toBe(shop.id);
  });

  it("requête sans X-Context (action par objet, contact…) : pas de rechargement ni de perte", async () => {
    const { result } = await start();
    server = all.filter((c) => c.id !== shop.id);
    deny("DENY_RELATION", false);
    await settle();
    expect(calls).toBe(0);
    expect(result.current.ctx.lost).toBeNull();
  });

  it("rafales de refus : un seul rechargement en vol", async () => {
    await start();
    deny("DENY_CONTEXT");
    deny("DENY_RELATION");
    deny("DENY_SECURITY");
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(1));
    await settle();
    expect(calls).toBe(1);
  });

  it("DENY_PERMISSION : réaligne les capacités sans jamais quitter le profil", async () => {
    const { result } = await start();
    expect(result.current.canLeave).toBe(true);
    server = all.map((c) => (c.id === shop.id ? { ...c, role: "ANALYST" as const, capabilities: ["org.view_internal", "org.leave", "stats.view", "offer.view_internal"] } : c));
    deny("DENY_PERMISSION");
    await waitFor(() => expect(result.current.canPublish).toBe(false));
    expect(result.current.ctx.active).toMatchObject({ id: shop.id, role: "ANALYST" });
    expect(result.current.ctx.lost).toBeNull();
  });
});
