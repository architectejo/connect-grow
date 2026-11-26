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
    expect(call("/api/v1/marketplace/posts/")).toBe(true);
    expect(call("/api/v1/marketplace/posts/12/")).toBe(true);
    expect(call("/api/v1/marketplace/sellers/organization/3/")).toBe(true);
    expect(call("/api/v1/marketplace/sellers/provider/3/")).toBe(true);
  });
  it("accepte la liste publique des organisations, avec filtres", () => {
    expect(call("/api/v1/accounts/organizations/")).toBe(true);
    expect(call("/api/v1/accounts/organizations/?org_type=ONG&claim=RCCM_VERIFIED&page=2")).toBe(true);
  });
  it("l'ancienne liste des entreprises n'est plus une lecture publique mise en cache", () => {
    expect(call("/api/v1/accounts/businesses/3/")).toBe(false);
  });
  it("l'ancien préfixe /api/ sans v1 n'est jamais mis en cache (L0-11)", () => {
    expect(call("/api/marketplace/posts/")).toBe(false);
    expect(call("/api/accounts/organizations/")).toBe(false);
  });
  it("les données privées restent hors cache sous /api/v1/ comme sous l'ancien préfixe", () => {
    for (const path of ["/api/v1/accounts/kyc/documents/", "/api/accounts/kyc/documents/", "/api/v1/interactions/notifications/", "/api/accounts/me/"]) {
      expect(call(path), path).toBe(false);
    }
  });
  it("refuse une requête authentifiée", () => {
    expect(call("/api/v1/marketplace/posts/", { Authorization: "Bearer x" })).toBe(false);
  });
  it("refuse my_posts, quelle que soit la valeur", () => {
    expect(call("/api/v1/marketplace/posts/?my_posts=true")).toBe(false);
    expect(call("/api/v1/marketplace/posts/?my_posts=false")).toBe(false);
    expect(call("/api/v1/marketplace/posts/?my_posts=")).toBe(false);
  });
  it("refuse la corbeille et mine", () => {
    expect(call("/api/v1/marketplace/posts/trash/")).toBe(false);
    expect(call("/api/v1/marketplace/posts/mine/")).toBe(false);
  });
  it("refuse les autres routes privées et les favoris", () => {
    expect(call("/api/v1/accounts/me/")).toBe(false);
    expect(call("/api/v1/accounts/kyc/")).toBe(false);
    expect(call("/api/v1/marketplace/favorites/")).toBe(false);
    expect(call("/api/v1/interactions/conversations/")).toBe(false);
  });
  it("refuse les méthodes autres que GET", () => {
    expect(call("/api/v1/marketplace/posts/", {}, "POST")).toBe(false);
  });
  it("refuse KYC et interactions, même sans en-tête Authorization", () => {
    expect(call("/api/v1/accounts/kyc/documents/")).toBe(false);
    expect(call("/api/v1/interactions/messages/?conversation=x")).toBe(false);
    expect(call("/api/v1/interactions/notifications/")).toBe(false);
  });
  it("refuse toute requête portant Authorization, y compris sur les routes publiques", () => {
    expect(call("/api/v1/accounts/organizations/", { Authorization: "Bearer x" })).toBe(false);
    expect(call("/api/v1/marketplace/sellers/user/3/", { Authorization: "Bearer x" })).toBe(false);
  });
});

describe("isContactRevealRequest (révélation du numéro : réseau seul)", () => {
  const match = (path: string) => isContactRevealRequest({ url: new URL(path, "http://localhost") });

  it("reconnaît reveal et reveals/received, avec ou sans /v1/ et paramètres", () => {
    expect(match("/api/v1/interactions/contacts/reveal/")).toBe(true);
    expect(match("/api/interactions/contacts/reveal/")).toBe(true);
    expect(match("/api/v2/interactions/contacts/reveal/")).toBe(true);
    expect(match("/api/v1/interactions/contacts/reveals/received/")).toBe(true);
    expect(match("/api/v1/interactions/contacts/reveals/received/?channel=CALL&page=2")).toBe(true);
  });
  it("ne couvre pas les autres routes", () => {
    expect(match("/api/v1/interactions/contacts/")).toBe(false);
    expect(match("/api/v1/marketplace/posts/")).toBe(false);
  });
  it("ces routes ne sont jamais éligibles au cache de contenus publics", () => {
    expect(call("/api/v1/interactions/contacts/reveals/received/")).toBe(false);
    expect(call("/api/v1/interactions/contacts/reveal/", {}, "POST")).toBe(false);
  });
  it("la configuration PWA la déclare en premier, en NetworkOnly", () => {
    const config = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf-8");
    // Premier objet du tableau runtimeCaching (sans accolade imbriquée) : urlPattern puis handler NetworkOnly
    expect(config).toMatch(/runtimeCaching:\s*\[\s*\{[^{}]*?urlPattern:\s*isContactRevealRequest,\s*handler:\s*"NetworkOnly"/);
  });
});

describe("configuration des fonctionnalités (L0-14)", () => {
  it("n'est jamais mise en cache hors ligne : seul le Cache-Control de 60 s du serveur s'applique", () => {
    expect(call("/api/v1/config/features/")).toBe(false);
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
    expect(match("/api/v1/accounts/contexts/")).toBe(true);
    expect(match("/api/accounts/contexts/")).toBe(true);
    expect(match("/api/v2/accounts/contexts/")).toBe(true);
    expect(match("/api/v1/accounts/contacts/")).toBe(false);
  });
  it("n'est jamais éligible au cache de contenus publics", () => {
    expect(call("/api/v1/accounts/contexts/")).toBe(false);
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
    `/api/v1/accounts/organizations/${ID}/internal/`,
    `/api/v1/accounts/organizations/${ID}/kyc/documents/`,
    `/api/v1/accounts/organizations/${ID}/kyc/documents/${ID}/`,
    `/api/v1/accounts/organizations/${ID}/verification/`,
    `/api/v1/accounts/organizations/${ID}/leave/`,
    `/api/v1/accounts/organizations/${ID}/archive/`,
    // Équipe (L1-01) : noms de personnes, réponses `no-store`
    `/api/v1/accounts/organizations/${ID}/members/`,
    `/api/v1/accounts/organizations/${ID}/members/?page=2`,
    `/api/v1/accounts/organizations/${ID}/members/${ID}/`,
    `/api/v1/accounts/organizations/${ID}/transfer-ownership/`,
    `/api/v1/accounts/organizations/${ID}/invitations/`,
    `/api/v1/accounts/organizations/${ID}/invitations/?status=PENDING&page=2`,
    `/api/v1/accounts/organizations/${ID}/invitations/${ID}/`,
    "/api/v1/accounts/organization-invitations/preview/",
    "/api/v1/accounts/organization-invitations/accept/",
    "/api/v1/accounts/organization-invitations/decline/",
    // Invitations v2 (L1-01-F2bis) : demandes à confirmer, code de rattachement, indice de téléphone
    `/api/v1/accounts/organizations/${ID}/invitations/?status=AWAITING_CONFIRMATION`,
    `/api/v1/accounts/organizations/${ID}/invitations/${ID}/confirm/`,
    `/api/v1/accounts/organizations/${ID}/invitations/${ID}/reject/`,
    "/api/v1/accounts/organization-invitations/awaiting/",
    "/api/v1/accounts/organization-invitations/awaiting/?page_size=10&page=2",
    `/api/v1/accounts/organization-invitations/${ID}/withdraw/`,
    `/api/v1/accounts/organization-invitations/${ID}/confirmation-code/`,
    `/api/v1/accounts/organizations/${ID}/`,
    "/api/v1/accounts/organizations/limits/",
    "/api/v1/accounts/provider/",
    "/api/v1/accounts/provider/activate/",
    "/api/v1/accounts/contexts/",
    "/api/v1/accounts/kyc/documents/",
    `/api/v1/accounts/organizations/${ID}/internal/`,
    "/api/v1/accounts/provider/",
  ];

  it.each(privatePaths)("%s n'est jamais éligible au cache de contenus publics, même sans Authorization", (path) => {
    expect(call(path)).toBe(false);
  });

  it("les routes sensibles (hors contexts, couvert plus haut) sont reconnues pour la règle NetworkOnly", () => {
    for (const path of privatePaths.filter((p) => !p.includes("/contexts/"))) expect(match(path), path).toBe(true);
  });

  it("reste en réseau seul sans v1 et sous une future v2", () => {
    for (const path of [`/api/accounts/organizations/${ID}/internal/`, `/api/v2/accounts/organizations/${ID}/internal/`, "/api/accounts/kyc/documents/", "/api/v2/accounts/kyc/documents/", "/api/v2/accounts/provider/"]) {
      expect(match(path), path).toBe(true);
    }
  });

  it("les routes d'équipe sont réseau seul, avec ou sans /v1/ et sous une future v2", () => {
    for (const path of [
      `/api/v1/accounts/organizations/${ID}/members/`,
      `/api/accounts/organizations/${ID}/members/${ID}/`,
      `/api/v2/accounts/organizations/${ID}/transfer-ownership/`,
    ]) {
      expect(match(path), path).toBe(true);
      expect(call(path), path).toBe(false);
      expect(call(path, {}, "POST"), path).toBe(false);
    }
  });

  it("les routes d'invitation (création, liste, révocation, échange du jeton) sont réseau seul, avec ou sans /v1/", () => {
    for (const path of [
      `/api/v1/accounts/organizations/${ID}/invitations/`,
      `/api/v1/accounts/organizations/${ID}/invitations/${ID}/`,
      "/api/v1/accounts/organization-invitations/preview/",
      "/api/accounts/organization-invitations/accept/",
      "/api/v2/accounts/organization-invitations/decline/",
    ]) {
      expect(match(path), path).toBe(true);
      expect(call(path), path).toBe(false);
      expect(call(path, {}, "POST"), path).toBe(false);
    }
  });

  it("la page /organization-invitation n'est pas une route d'API et le jeton (fragment) n'atteint jamais le service worker", () => {
    expect(match("/organization-invitation")).toBe(false);
    expect(call("/organization-invitation")).toBe(false);
    // Un fragment n'est jamais envoyé au réseau : l'URL vue par le service worker n'en contient pas
    expect(new URL("http://localhost/organization-invitation#token=abc").search).toBe("");
  });

  it("la liste publique des organisations n'est pas une route sensible", () => {
    expect(match("/api/v1/accounts/organizations/")).toBe(false);
    expect(match("/api/v1/accounts/organizations/?search=a")).toBe(false);
    expect(match("/api/v1/marketplace/sellers/organization/3/")).toBe(false);
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
