import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { isCacheableApiContent, isContactRevealRequest, isContextsRequest, isSensitiveIdentityRequest } from "./cache-rules";

const call = (path: string, headers: Record<string, string> = {}, method = "GET") =>
  isCacheableApiContent({
    url: new URL(path, "http://localhost"),
    request: new Request("http://localhost" + path, { method, headers }),
  });

describe("isCacheableApiContent", () => {
  it("accepte une lecture publique", () => {
    expect(call("/api/marketplace/posts/")).toBe(true);
    expect(call("/api/v1/marketplace/posts/12/")).toBe(true);
    expect(call("/api/marketplace/sellers/organization/3/")).toBe(true);
    expect(call("/api/v1/marketplace/sellers/provider/3/")).toBe(true);
  });
  it("accepte la liste publique des organisations, avec filtres", () => {
    expect(call("/api/accounts/organizations/")).toBe(true);
    expect(call("/api/v1/accounts/organizations/?org_type=ONG&claim=RCCM_VERIFIED&page=2")).toBe(true);
  });
  it("l'ancienne liste des entreprises n'est plus une lecture publique mise en cache", () => {
    expect(call("/api/accounts/businesses/3/")).toBe(false);
  });
  it("refuse une requête authentifiée", () => {
    expect(call("/api/marketplace/posts/", { Authorization: "Bearer x" })).toBe(false);
  });
  it("refuse my_posts, quelle que soit la valeur", () => {
    expect(call("/api/marketplace/posts/?my_posts=true")).toBe(false);
    expect(call("/api/marketplace/posts/?my_posts=false")).toBe(false);
    expect(call("/api/marketplace/posts/?my_posts=")).toBe(false);
  });
  it("refuse la corbeille et mine", () => {
    expect(call("/api/marketplace/posts/trash/")).toBe(false);
    expect(call("/api/v1/marketplace/posts/mine/")).toBe(false);
  });
  it("refuse les autres routes privées et les favoris", () => {
    expect(call("/api/accounts/me/")).toBe(false);
    expect(call("/api/accounts/kyc/")).toBe(false);
    expect(call("/api/marketplace/favorites/")).toBe(false);
    expect(call("/api/interactions/conversations/")).toBe(false);
  });
  it("refuse les méthodes autres que GET", () => {
    expect(call("/api/marketplace/posts/", {}, "POST")).toBe(false);
  });
  it("refuse KYC et interactions, même sans en-tête Authorization", () => {
    expect(call("/api/accounts/kyc/documents/")).toBe(false);
    expect(call("/api/v1/interactions/messages/?conversation=x")).toBe(false);
    expect(call("/api/interactions/notifications/")).toBe(false);
  });
  it("refuse toute requête portant Authorization, y compris sur les routes publiques", () => {
    expect(call("/api/accounts/organizations/", { Authorization: "Bearer x" })).toBe(false);
    expect(call("/api/marketplace/sellers/user/3/", { Authorization: "Bearer x" })).toBe(false);
  });
});

describe("isContactRevealRequest (révélation du numéro : réseau seul)", () => {
  const match = (path: string) => isContactRevealRequest({ url: new URL(path, "http://localhost") });

  it("reconnaît reveal et reveals/received, avec ou sans /v1/ et paramètres", () => {
    expect(match("/api/interactions/contacts/reveal/")).toBe(true);
    expect(match("/api/v1/interactions/contacts/reveal/")).toBe(true);
    expect(match("/api/interactions/contacts/reveals/received/")).toBe(true);
    expect(match("/api/interactions/contacts/reveals/received/?channel=CALL&page=2")).toBe(true);
  });
  it("ne couvre pas les autres routes", () => {
    expect(match("/api/interactions/contacts/")).toBe(false);
    expect(match("/api/marketplace/posts/")).toBe(false);
  });
  it("ces routes ne sont jamais éligibles au cache de contenus publics", () => {
    expect(call("/api/interactions/contacts/reveals/received/")).toBe(false);
    expect(call("/api/interactions/contacts/reveal/", {}, "POST")).toBe(false);
  });
  it("la configuration PWA la déclare en premier, en NetworkOnly", () => {
    const config = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf-8");
    // Premier objet du tableau runtimeCaching (sans accolade imbriquée) : urlPattern puis handler NetworkOnly
    expect(config).toMatch(/runtimeCaching:\s*\[\s*\{[^{}]*?urlPattern:\s*isContactRevealRequest,\s*handler:\s*"NetworkOnly"/);
  });
});

describe("configuration des fonctionnalités (L0-14)", () => {
  it("n'est jamais mise en cache hors ligne : seul le Cache-Control de 60 s du serveur s'applique", () => {
    expect(call("/api/config/features/")).toBe(false);
    expect(call("/api/v1/config/features/")).toBe(false);
  });
  it("aucune règle Workbox de vite.config.ts ne cible config/features", () => {
    const config = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf-8");
    expect(config).not.toMatch(/config\/features/);
  });
});

describe("liste des profils (accounts/contexts/) : jamais en cache hors ligne", () => {
  const match = (path: string) => isContextsRequest({ url: new URL(path, "http://localhost") });

  it("reconnaît contexts/ avec ou sans /v1/", () => {
    expect(match("/api/accounts/contexts/")).toBe(true);
    expect(match("/api/v1/accounts/contexts/")).toBe(true);
    expect(match("/api/accounts/contacts/")).toBe(false);
  });
  it("n'est jamais éligible au cache de contenus publics", () => {
    expect(call("/api/accounts/contexts/")).toBe(false);
    expect(call("/api/v1/accounts/contexts/")).toBe(false);
  });
  it("la configuration PWA la déclare en NetworkOnly, avant toute règle de cache", () => {
    const config = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf-8");
    const rule = config.search(/urlPattern:\s*isContextsRequest,\s*handler:\s*"NetworkOnly"/);
    expect(rule).toBeGreaterThan(-1);
    expect(rule).toBeLessThan(config.indexOf('handler: "CacheFirst"'));
    expect(rule).toBeLessThan(config.indexOf('handler: "StaleWhileRevalidate"'));
    expect(rule).toBeLessThan(config.indexOf('handler: "NetworkFirst"'));
  });
});

describe("espace d'une organisation, prestataire et pièces : jamais en cache hors ligne", () => {
  const match = (path: string) => isSensitiveIdentityRequest({ url: new URL(path, "http://localhost") });
  const ID = "11111111-1111-4111-8111-111111111111";
  const privatePaths = [
    `/api/accounts/organizations/${ID}/internal/`,
    `/api/accounts/organizations/${ID}/kyc/documents/`,
    `/api/accounts/organizations/${ID}/kyc/documents/${ID}/`,
    `/api/accounts/organizations/${ID}/verification/`,
    `/api/accounts/organizations/${ID}/leave/`,
    `/api/accounts/organizations/${ID}/archive/`,
    `/api/accounts/organizations/${ID}/`,
    "/api/accounts/organizations/limits/",
    "/api/accounts/provider/",
    "/api/accounts/provider/activate/",
    "/api/accounts/contexts/",
    "/api/accounts/kyc/documents/",
    `/api/v1/accounts/organizations/${ID}/internal/`,
    "/api/v1/accounts/provider/",
  ];

  it.each(privatePaths)("%s n'est jamais éligible au cache de contenus publics, même sans Authorization", (path) => {
    expect(call(path)).toBe(false);
  });

  it("les routes sensibles (hors contexts, couvert plus haut) sont reconnues pour la règle NetworkOnly", () => {
    for (const path of privatePaths.filter((p) => !p.includes("/contexts/"))) expect(match(path), path).toBe(true);
  });

  it("la liste publique des organisations n'est pas une route sensible", () => {
    expect(match("/api/accounts/organizations/")).toBe(false);
    expect(match("/api/accounts/organizations/?search=a")).toBe(false);
    expect(match("/api/marketplace/sellers/organization/3/")).toBe(false);
  });

  it("la configuration PWA la déclare en NetworkOnly, avant toute règle de cache", () => {
    const config = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf-8");
    const rule = config.search(/urlPattern:\s*isSensitiveIdentityRequest,\s*handler:\s*"NetworkOnly"/);
    expect(rule).toBeGreaterThan(-1);
    expect(rule).toBeLessThan(config.indexOf('handler: "CacheFirst"'));
    expect(rule).toBeLessThan(config.indexOf('handler: "StaleWhileRevalidate"'));
    expect(rule).toBeLessThan(config.indexOf('handler: "NetworkFirst"'));
  });
});
