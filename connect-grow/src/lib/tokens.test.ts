import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { POST_DRAFT_KEY, API_CONTENT_CACHE, tokenStorage } from "./tokens";

describe("tokenStorage.clear", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("supprime jetons, brouillon d'annonce et anciennes clés utilisateur", () => {
    tokenStorage.set("a", "r");
    localStorage.setItem(POST_DRAFT_KEY, "{}");
    localStorage.setItem("user_full_name", "X");
    localStorage.setItem("user_id", "1");
    localStorage.setItem("autre", "garde");
    tokenStorage.clear();
    expect(tokenStorage.getAccess()).toBeNull();
    expect(tokenStorage.getRefresh()).toBeNull();
    expect(localStorage.getItem(POST_DRAFT_KEY)).toBeNull();
    expect(localStorage.getItem("user_full_name")).toBeNull();
    expect(localStorage.getItem("user_id")).toBeNull();
    expect(localStorage.getItem("autre")).toBe("garde");
  });

  it("purge le cache PWA des annonces", () => {
    const del = vi.fn().mockResolvedValue(true);
    vi.stubGlobal("caches", { delete: del });
    tokenStorage.clear();
    expect(del).toHaveBeenCalledWith(API_CONTENT_CACHE);
  });

  it("purge tous les caches applicatifs (annonces, référentiels, photos)", () => {
    const del = vi.fn().mockResolvedValue(true);
    vi.stubGlobal("caches", { delete: del });
    tokenStorage.clear();
    expect(del.mock.calls.map((c) => c[0]).sort()).toEqual(["api-annonces", "api-annonces-v2", "api-referentiels", "photos"]);
  });

  it("ne plante pas si l'API Cache est indisponible", () => {
    vi.stubGlobal("caches", undefined);
    expect(() => tokenStorage.clear()).not.toThrow();
  });

  it("ne produit pas d'erreur non gérée si caches.delete rejette", async () => {
    const del = vi.fn().mockRejectedValue(new Error("refus"));
    vi.stubGlobal("caches", { delete: del });
    expect(() => tokenStorage.clear()).not.toThrow();
    await new Promise((r) => setTimeout(r, 0));
    expect(del).toHaveBeenCalled();
  });
});
