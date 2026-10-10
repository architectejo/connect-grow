import type { ContextType } from "@/api/types";

/** Nom de l'en-tête du profil actif (ADR 0006 §6.1). */
export const CONTEXT_HEADER = "X-Context";

/** UUID au format canonique minuscule, seul format accepté par le serveur. */
export const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const API_VERSION_PREFIX = /^(?:\/?api)?\/?(?:v\d+\/)?/;

/** Chemin relatif à l'API (sans domaine, requête, ni préfixe `api/` ou `v1/`), ou null. */
function apiPath(url: string | undefined): string | null {
  if (!url) return null;
  let path = url;
  try {
    path = new URL(url, "http://local.invalid").pathname;
  } catch {
    return null;
  }
  return path.replace(API_VERSION_PREFIX, "").replace(/^\/+/, "");
}

const truthy = (value: unknown) => value === true || (typeof value === "string" && value.toLowerCase() === "true");

/**
 * Appels « de mon profil actif » (ADR 0006 §6.4, première ligne du tableau) : seuls ceux-là lisent X-Context.
 * Tout le reste est par objet (le serveur déduit le profil de l'objet) ou toujours personnel (contact, avis,
 * favoris, signalement, me/, notifications) : l'en-tête n'y est jamais envoyé.
 * Les listes de « mes offres » passent par `posts/?my_posts=true` (nom réel du paramètre) ou `mine=true`.
 */
export function isContextScopedRequest(method: string | undefined, url: string | undefined, params?: unknown): boolean {
  const path = apiPath(url);
  if (path === null) return false;
  const verb = (method ?? "get").toUpperCase();
  const normalized = path.replace(/\/+$/, "");

  if (normalized === "marketplace/posts") {
    if (verb === "POST") return true; // création d'offre
    if (verb !== "GET") return false;
    const fromUrl = new URL(url as string, "http://local.invalid").searchParams;
    const fromParams = (params ?? {}) as Record<string, unknown>;
    return truthy(fromUrl.get("my_posts")) || truthy(fromUrl.get("mine")) || truthy(fromParams.my_posts) || truthy(fromParams.mine);
  }
  if (verb === "GET" && normalized === "marketplace/posts/trash") return true;
  if (verb === "GET" && normalized === "marketplace/stats/dashboard") return true;
  if (normalized === "accounts/contact-settings" || normalized.startsWith("accounts/contact-settings/")) return true;
  if (verb === "GET" && normalized === "interactions/contacts/reveals/received") return true; // « qui a demandé »
  if (verb === "GET" && normalized === "interactions/conversations") return true; // boîte de messages
  return false;
}

/** Valeur de l'en-tête pour un profil, ou undefined (personnel : en-tête absent ; identifiant invalide : jamais envoyé). */
export function contextHeaderValue(selection: { type: ContextType; id: string } | null | undefined): string | undefined {
  if (!selection || selection.type === "USER") return undefined;
  if (selection.type !== "PROVIDER" && selection.type !== "ORGANIZATION") return undefined;
  return CANONICAL_UUID.test(selection.id) ? `${selection.type}:${selection.id}` : undefined;
}
