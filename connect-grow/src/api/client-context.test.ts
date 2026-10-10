import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CONTEXT_DENIED_EVENT, activeContextStore, toSelection, type ContextDeniedDetail } from "@/lib/active-context";
import { tokenStorage } from "@/lib/tokens";
import type { AvailableContext } from "@/api/types";
import fixture from "./__fixtures__/contexts.json";
import apiClient, { resetRefreshState } from "./client";

const [personal, provider, shop] = fixture.response.results as AvailableContext[];

describe("en-tête X-Context du client API", () => {
  let seen: Record<string, unknown>[];
  let respond: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;
  const original = apiClient.defaults.adapter;
  const ok = (config: InternalAxiosRequestConfig) => Promise.resolve({ data: {}, status: 200, statusText: "", headers: {}, config } as AxiosResponse);

  beforeEach(() => {
    localStorage.clear();
    activeContextStore._resetForTests();
    resetRefreshState();
    seen = [];
    respond = ok;
    apiClient.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      seen.push({ url: config.url, header: config.headers["X-Context"] });
      return respond(config);
    }) as AxiosAdapter;
    tokenStorage.set("acces", "refresh");
  });
  afterEach(() => {
    apiClient.defaults.adapter = original;
    vi.restoreAllMocks();
  });

  const headerOf = (index = 0) => seen[index].header;

  it("profil personnel : jamais d'en-tête, même sur les appels « de mon profil »", async () => {
    activeContextStore.set(toSelection(personal.id, personal));
    await apiClient.get("marketplace/posts/trash/");
    await apiClient.post("marketplace/posts/", {});
    expect(headerOf(0)).toBeUndefined();
    expect(headerOf(1)).toBeUndefined();
  });

  it("organisation active : en-tête TYPE:uuid sur création d'offre, corbeille, statistiques, réglages, boîte, « qui a demandé »", async () => {
    activeContextStore.set(toSelection(personal.id, shop));
    await apiClient.post("marketplace/posts/", {});
    await apiClient.get("marketplace/posts/trash/");
    await apiClient.get("marketplace/stats/dashboard/");
    await apiClient.get("accounts/contact-settings/");
    await apiClient.get("interactions/conversations/");
    await apiClient.get("interactions/contacts/reveals/received/", { params: { page: 2 } });
    await apiClient.get("marketplace/posts/", { params: { my_posts: "true" } });
    expect(seen).toHaveLength(7);
    for (const call of seen) expect(call.header).toBe(`ORGANIZATION:${shop.id}`);
  });

  it("prestataire actif : PROVIDER:uuid", async () => {
    activeContextStore.set(toSelection(personal.id, provider));
    await apiClient.get("marketplace/stats/dashboard/");
    expect(headerOf()).toBe(`PROVIDER:${provider.id}`);
  });

  it("jamais pour contact, avis, favoris, signalement, notifications, me/, offres publiques", async () => {
    activeContextStore.set(toSelection(personal.id, shop));
    await apiClient.post("interactions/contacts/", {});
    await apiClient.post("interactions/contacts/reveal/", {});
    await apiClient.post("interactions/reviews/", {});
    await apiClient.post("marketplace/posts/p1/favorite/");
    await apiClient.get("marketplace/favorites/");
    await apiClient.post("moderation/reports/", {});
    await apiClient.get("interactions/notifications/");
    await apiClient.get("accounts/me/");
    await apiClient.get("accounts/contexts/");
    await apiClient.get("marketplace/posts/");
    await apiClient.patch("marketplace/posts/p1/", {});
    expect(seen.every((call) => call.header === undefined)).toBe(true);
  });

  it("pas d'en-tête sans jeton (visiteur)", async () => {
    tokenStorage.clear();
    activeContextStore.set(toSelection(personal.id, shop));
    await apiClient.get("marketplace/posts/trash/");
    expect(headerOf()).toBeUndefined();
  });

  it("le profil actif est relu à chaque requête (changement immédiat)", async () => {
    activeContextStore.set(toSelection(personal.id, shop));
    await apiClient.get("marketplace/stats/dashboard/");
    activeContextStore.set(toSelection(personal.id, provider));
    await apiClient.get("marketplace/stats/dashboard/");
    activeContextStore.set(null);
    await apiClient.get("marketplace/stats/dashboard/");
    expect(seen.map((call) => call.header)).toEqual([`ORGANIZATION:${shop.id}`, `PROVIDER:${provider.id}`, undefined]);
  });

  describe("refus DENY_*", () => {
    const capture = () => {
      const events: ContextDeniedDetail[] = [];
      const listener = (event: Event) => events.push((event as CustomEvent<ContextDeniedDetail>).detail);
      window.addEventListener(CONTEXT_DENIED_EVENT, listener);
      return { events, stop: () => window.removeEventListener(CONTEXT_DENIED_EVENT, listener) };
    };
    const refuse = (code: string) => (config: InternalAxiosRequestConfig) =>
      Promise.reject(new AxiosError("403", "403", config, null, { status: 403, data: { detail: "x", code }, headers: {}, config, statusText: "" } as AxiosResponse));

    it("signale le code et si la requête portait X-Context", async () => {
      const { events, stop } = capture();
      activeContextStore.set(toSelection(personal.id, shop));
      respond = refuse("DENY_RELATION");
      await expect(apiClient.get("marketplace/posts/trash/")).rejects.toBeTruthy();
      await expect(apiClient.get("marketplace/favorites/")).rejects.toBeTruthy();
      stop();
      expect(events).toEqual([
        { code: "DENY_RELATION", sentContext: true },
        { code: "DENY_RELATION", sentContext: false },
      ]);
    });

    it("n'émet rien pour un 403 sans code DENY ni pour un autre statut", async () => {
      const { events, stop } = capture();
      respond = refuse("autre_chose");
      await expect(apiClient.get("marketplace/posts/trash/")).rejects.toBeTruthy();
      respond = (config) => Promise.reject(new AxiosError("500", "500", config, null, { status: 500, data: { code: "DENY_CONTEXT" }, headers: {}, config, statusText: "" } as AxiosResponse));
      await expect(apiClient.get("marketplace/posts/trash/")).rejects.toBeTruthy();
      stop();
      expect(events).toEqual([]);
    });
  });
});
