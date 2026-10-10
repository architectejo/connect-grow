/**
 * Recette L0-10a (front) : règle 10, le numéro du vendeur n'est jamais dans la page avant le clic,
 * ne survit pas à la fermeture, et les routes qui le portent ne sont jamais mises en cache par le
 * service worker. Cohérence des codes d'erreur avec le serveur (ADR 0005 §5.4).
 *
 * Fichier .ts : les composants sont créés avec createElement.
 */
import { createElement, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { ContactChannel, RevealedContact } from "@/api/types";
import { ContactActions } from "@/components/post/ContactActions";
import { isCacheableApiContent, isContactRevealRequest } from "@/lib/cache-rules";
import { revealErrorInfo, revealLink } from "@/lib/contact-reveal";

const auth = vi.hoisted(() => ({ isAuthenticated: true }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

const OFFER = "11111111-1111-4111-8111-111111111111";
const PHONE = "+243897654321";
const DIGITS = "243897654321";
const LAST4 = "4321";

const callResult: RevealedContact = {
  contact_event_id: "22222222-2222-4222-8222-222222222222",
  channel: "CALL",
  created: true,
  phone: PHONE,
  tel_url: `tel:${PHONE}`,
  whatsapp_url: null,
};
const whatsappResult: RevealedContact = {
  ...callResult,
  channel: "WHATSAPP",
  tel_url: null,
  whatsapp_url: `https://wa.me/${DIGITS}?text=Un%20joli%20canap%C3%A9`,
};

const apiError = (status: number, code: string, headers: Record<string, string> = {}) =>
  Object.assign(new Error(code), { response: { status, data: { detail: "x", code }, headers } });

function renderActions(allowed: ContactChannel[], layout: "stack" | "bar" = "stack") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(MemoryRouter, { initialEntries: [`/post/${OFFER}`] }, createElement(QueryClientProvider, { client }, children));
  const view = render(
    createElement(ContactActions, { offerId: OFFER, sellerName: "Marie", allowedChannels: allowed, layout, onMessage: vi.fn() }),
    { wrapper },
  );
  return { ...view, client };
}

const noPhoneInPage = () => {
  const html = document.body.innerHTML;
  expect(html).not.toMatch(/tel:|wa\.me|\+243|href="javascript/i);
  expect(html).not.toContain(DIGITS);
  expect(html).not.toContain(LAST4);
  expect(html).not.toMatch(/\d{7,}/); // aucune suite de chiffres ressemblant à un numéro
};

describe("recette contact : scénario 9 (aucun numéro dans le DOM avant le clic)", () => {
  beforeEach(() => {
    auth.isAuthenticated = true;
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it.each(["stack", "bar"] as const)("tous moyens autorisés : ni lien, ni numéro, ni tel:/wa.me dans la page (%s)", (layout) => {
    const post = vi.spyOn(apiClient, "post");
    const { container } = renderActions(["MESSAGE", "CALL", "WHATSAPP"], layout);
    expect(container.querySelectorAll("a[href]")).toHaveLength(0);
    noPhoneInPage();
    expect(post).not.toHaveBeenCalled();
  });

  it("l'ouverture de la boîte de dialogue ne déclenche aucun appel ni ne montre de numéro", () => {
    const post = vi.spyOn(apiClient, "post");
    const get = vi.spyOn(apiClient, "get");
    renderActions(["CALL", "WHATSAPP"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    noPhoneInPage();
    expect(post).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
  });

  it("double clic rapproché sur « Afficher le numéro » : une seule requête", async () => {
    let resolveRequest: (value: unknown) => void = () => undefined;
    const post = vi.spyOn(apiClient, "post").mockImplementation(() => new Promise((resolve) => (resolveRequest = resolve)));
    renderActions(["CALL"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    const show = screen.getByRole("button", { name: "Afficher le numéro" });
    // Double clic humain : les clics sont des tâches distinctes (quelques dizaines de ms), pas le même tour de boucle.
    fireEvent.click(show);
    await waitFor(() => expect(post).toHaveBeenCalled());
    for (let i = 0; i < 2; i++) {
      await new Promise((done) => setTimeout(done, 30));
      fireEvent.click(show);
    }
    await new Promise((done) => setTimeout(done, 50));
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => resolveRequest({ data: callResult }));
    expect(await screen.findByTestId("revealed-phone")).toHaveTextContent(PHONE);
  });

  it("le numéro n'apparaît qu'après la réponse, puis disparaît partout à la fermeture", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: whatsappResult });
    const { client, unmount } = renderActions(["WHATSAPP"]);
    fireEvent.click(screen.getByRole("button", { name: /WhatsApp/ }));
    noPhoneInPage();
    fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
    expect(await screen.findByTestId("revealed-phone")).toHaveTextContent(PHONE);
    expect(screen.getByRole("link", { name: "Ouvrir WhatsApp" })).toHaveAttribute("rel", "noopener noreferrer");

    // Aucune persistance.
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("243");
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.state.data))).not.toContain("243");
    expect(document.cookie).not.toContain("243");

    fireEvent.click(screen.getByRole("button", { name: "Fermer" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    noPhoneInPage();
    expect(JSON.stringify(client.getMutationCache().getAll().map((m) => m.state.data ?? null))).not.toContain("243");
    unmount();
    expect(document.body.innerHTML).not.toContain(DIGITS);
  });

  it("canal retiré par le vendeur (403) : message français, aucun numéro, le repli par message est proposé", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(403, "channel_not_allowed"));
    renderActions(["MESSAGE", "CALL"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/n'accepte pas ce moyen/);
    expect(screen.getByRole("button", { name: "Écrire un message à la place" })).toBeInTheDocument();
    noPhoneInPage();
  });

  it("réseau coupé : message de connexion, réessai possible, aucun numéro", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(Object.assign(new Error("Network Error"), { response: undefined }));
    renderActions(["CALL"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
    noPhoneInPage();
  });

  it("un lien venu du serveur hors liste blanche n'est jamais rendu", () => {
    for (const bad of ["javascript:alert(1)", "tel:+243897654321;ext=1", "https://evil.example/243897654321", "data:text/html,x"]) {
      expect(revealLink("CALL", { tel_url: bad, whatsapp_url: null })).toBeNull();
      expect(revealLink("WHATSAPP", { tel_url: null, whatsapp_url: bad })).toBeNull();
    }
    expect(revealLink("WHATSAPP", { tel_url: null, whatsapp_url: "https://wa.me/243897654321.evil.example" })).toBeNull();
    expect(revealLink("CALL", { tel_url: callResult.tel_url, whatsapp_url: null })).toBe(`tel:${PHONE}`);
  });
});

describe("recette contact : scénario 9 (service worker)", () => {
  const dist = resolve(__dirname, "../../dist/sw.js");
  const url = (path: string) => new URL(path, "http://localhost");

  it("la règle de non-cache couvre reveal et reveals/received, toutes méthodes, avec ou sans /v1", () => {
    for (const path of [
      "/api/interactions/contacts/reveal/",
      "/api/interactions/contacts/reveal",
      "/api/v1/interactions/contacts/reveal/",
      "/api/interactions/contacts/reveals/received/",
      "/api/v1/interactions/contacts/reveals/received/",
    ]) {
      expect(isContactRevealRequest({ url: url(path) }), path).toBe(true);
    }
    expect(isContactRevealRequest({ url: url("/api/accounts/contact-settings/") })).toBe(false);
  });

  it("aucune de ces routes (ni les réglages de contact) n'est mise en cache par la règle de lecture publique", () => {
    for (const path of [
      "/api/interactions/contacts/reveals/received/?page=2",
      "/api/interactions/contacts/reveal/",
      "/api/accounts/contact-settings/",
    ]) {
      const request = new Request("http://localhost" + path);
      expect(isCacheableApiContent({ url: url(path), request }), path).toBe(false);
    }
  });

  it("vite.config.ts : la règle NetworkOnly est la première de runtimeCaching", () => {
    const source = readFileSync(resolve(__dirname, "../../vite.config.ts"), "utf-8");
    const block = source.slice(source.indexOf("runtimeCaching"));
    const first = /urlPattern:\s*([A-Za-z]+)[\s\S]*?handler:\s*"([A-Za-z]+)"/.exec(block);
    expect(first?.[1]).toBe("isContactRevealRequest");
    expect(first?.[2]).toBe("NetworkOnly");
  });

  it.skipIf(!existsSync(dist))("dist/sw.js : NetworkOnly enregistré avant tout autre cache et motif de la règle présent", () => {
    const sw = readFileSync(dist, "utf-8");
    expect([...sw.matchAll(/registerRoute\(/g)].length).toBeGreaterThan(2);
    // La règle NetworkOnly du motif des numéros précède toute stratégie de cache (Workbox applique la première qui correspond).
    const pattern = String.raw`contacts\/(reveal|reveals\/received)`;
    const rule = sw.indexOf(pattern);
    expect(rule).toBeGreaterThan(-1);
    const strategy = /new e\.(NetworkOnly|CacheFirst|StaleWhileRevalidate|NetworkFirst)/g;
    const first = [...sw.matchAll(strategy)][0];
    expect(first[1]).toBe("NetworkOnly"); // la toute première stratégie du fichier
    expect(first.index).toBeGreaterThan(rule);
    expect((first.index ?? 0) - rule).toBeLessThan(200); // et elle est bien attachée à ce motif
    const next = sw.slice(rule).match(/new e\.NetworkOnly/);
    expect(next).not.toBeNull();
    // Le motif des numéros n'est associé à aucune autre stratégie.
    expect(sw.split(pattern).length - 1).toBe(1);
  });
});

describe("recette contact : scénario 10 (codes d'erreur)", () => {
  it.each([
    ["channel_invalid", 400, "blocked"],
    ["own_offer", 403, "blocked"],
    ["contact_restricted", 403, "blocked"],
    ["channel_not_allowed", 403, "unavailable"],
    ["offer_not_found", 404, "unavailable"],
    ["reveal_quota_account", 429, "limit"],
    ["reveal_quota_new_account", 429, "limit"],
    ["reveal_quota_ip", 429, "limit"],
    ["reveal_in_progress", 409, "retry"],
  ])("%s (%i) -> %s, en français, sans anglais DRF ni numéro", (code, status, kind) => {
    const info = revealErrorInfo(apiError(status, code, { "Retry-After": "120" }));
    expect(info.kind).toBe(kind);
    expect(info.message).toMatch(/[a-zé]/i);
    expect(info.message).not.toMatch(/\b(throttled|forbidden|not found|Expected available)\b/i);
    expect(info.message).not.toMatch(/reveal\.errors|undefined|\{\{/); // clé i18n manquante ou variable non résolue
  });

  it("401 invite à se connecter ; 5xx et réseau permettent de réessayer", () => {
    expect(revealErrorInfo(apiError(401, "not_authenticated")).kind).toBe("login");
    expect(revealErrorInfo(apiError(500, "x")).kind).toBe("retry");
    expect(revealErrorInfo({ response: undefined }).kind).toBe("retry");
  });

  it("le délai affiché suit Retry-After (120 s -> 2 minutes ; 7200 s -> 2 heures)", () => {
    expect(revealErrorInfo(apiError(429, "reveal_quota_ip", { "Retry-After": "120" })).message).toMatch(/2 minutes/);
    expect(revealErrorInfo(apiError(429, "reveal_quota_account", { "Retry-After": "7200" })).message).toMatch(/2 heures/);
  });

  it("le serveur répond en toute lettres : les codes de l'ADR 5.4 sont exactement ceux gérés par le front", () => {
    const source = readFileSync(resolve(__dirname, "../lib/contact-reveal.ts"), "utf-8");
    const handled = [...source.matchAll(/case "([a-z_]+)":/g)].map((m) => m[1]).sort();
    expect(handled).toEqual(
      ["channel_invalid", "channel_not_allowed", "contact_restricted", "offer_not_found", "own_offer", "reveal_in_progress",
        "reveal_quota_account", "reveal_quota_ip", "reveal_quota_new_account"].sort(),
    );
  });
});
