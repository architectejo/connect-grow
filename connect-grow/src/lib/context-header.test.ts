import { describe, expect, it } from "vitest";
import { contextHeaderValue, isContextScopedRequest } from "./context-header";

describe("liste blanche des appels « de mon profil » (ADR 0006 §6.4)", () => {
  it.each([
    ["post", "marketplace/posts/"],
    ["get", "marketplace/posts/trash/"],
    ["get", "marketplace/stats/dashboard/"],
    ["get", "accounts/contact-settings/"],
    ["put", "accounts/contact-settings/phone/"],
    ["post", "accounts/contact-settings/phone/verify/"],
    ["put", "accounts/contact-settings/channels/CALL/"],
    ["get", "interactions/contacts/reveals/received/"],
    ["get", "interactions/conversations/"],
  ])("%s %s : l'en-tête est envoyé", (method, url) => {
    expect(isContextScopedRequest(method, url)).toBe(true);
  });

  it("liste « mes offres » : my_posts=true (paramètre réel) ou mine=true, en paramètre ou dans l'URL", () => {
    expect(isContextScopedRequest("get", "marketplace/posts/", { my_posts: "true" })).toBe(true);
    expect(isContextScopedRequest("get", "marketplace/posts/", { mine: true })).toBe(true);
    expect(isContextScopedRequest("get", "marketplace/posts/?my_posts=true")).toBe(true);
    expect(isContextScopedRequest("GET", "marketplace/posts?mine=true")).toBe(true);
  });

  it("la liste publique des offres n'envoie jamais le profil", () => {
    expect(isContextScopedRequest("get", "marketplace/posts/")).toBe(false);
    expect(isContextScopedRequest("get", "marketplace/posts/", { category: "x" })).toBe(false);
    expect(isContextScopedRequest("get", "marketplace/posts/", { my_posts: "false" })).toBe(false);
  });

  it.each([
    ["post", "interactions/contacts/"], // contact
    ["post", "interactions/contacts/reveal/"], // révélation du numéro
    ["post", "interactions/exchanges/"],
    ["get", "interactions/reviews/"], // avis
    ["post", "interactions/reviews/"],
    ["post", "marketplace/posts/abc/favorite/"], // favoris
    ["get", "marketplace/favorites/"],
    ["post", "moderation/reports/"], // signalement
    ["get", "accounts/me/"],
    ["patch", "accounts/me/"],
    ["get", "interactions/notifications/"],
    ["get", "accounts/contexts/"],
    ["get", "interactions/messages/"], // lecture d'une conversation : par objet
    ["post", "interactions/messages/"], // envoi : par objet
  ])("%s %s : jamais d'en-tête", (method, url) => {
    expect(isContextScopedRequest(method, url)).toBe(false);
  });

  it("les actions par objet sur une offre n'envoient pas le profil", () => {
    expect(isContextScopedRequest("patch", "marketplace/posts/123/")).toBe(false);
    expect(isContextScopedRequest("delete", "marketplace/posts/123/")).toBe(false);
    expect(isContextScopedRequest("post", "marketplace/posts/123/soft_delete/")).toBe(false);
    expect(isContextScopedRequest("get", "marketplace/stats/post/123/")).toBe(false);
  });

  it("reconnaît les URL absolues, le préfixe /api/ et /v1/", () => {
    expect(isContextScopedRequest("get", "http://localhost:8000/api/marketplace/posts/trash/")).toBe(true);
    expect(isContextScopedRequest("get", "/api/v1/interactions/conversations/")).toBe(true);
    expect(isContextScopedRequest("get", "http://localhost:8000/api/config/features/")).toBe(false);
  });

  it("URL absente : pas d'en-tête", () => {
    expect(isContextScopedRequest("get", undefined)).toBe(false);
  });
});

describe("contextHeaderValue", () => {
  const id = "33333333-3333-4333-8333-333333333333";
  it("format TYPE:uuid pour un prestataire ou une organisation", () => {
    expect(contextHeaderValue({ type: "ORGANIZATION", id })).toBe(`ORGANIZATION:${id}`);
    expect(contextHeaderValue({ type: "PROVIDER", id })).toBe(`PROVIDER:${id}`);
  });
  it("profil personnel ou absent : en-tête absent", () => {
    expect(contextHeaderValue({ type: "USER", id })).toBeUndefined();
    expect(contextHeaderValue(null)).toBeUndefined();
  });
  it("n'envoie jamais un identifiant qui n'est pas un UUID canonique minuscule", () => {
    expect(contextHeaderValue({ type: "ORGANIZATION", id: "abcdef01-abcd-4bcd-8bcd-abcdefabcdef".toUpperCase() })).toBeUndefined();
    expect(contextHeaderValue({ type: "ORGANIZATION", id: "abcdef01-abcd-4bcd-8bcd-abcdefabcdef" })).toBeDefined();
    expect(contextHeaderValue({ type: "ORGANIZATION", id: "" })).toBeUndefined();
    expect(contextHeaderValue({ type: "ORGANIZATION", id: `{${id}}` })).toBeUndefined();
  });
});
