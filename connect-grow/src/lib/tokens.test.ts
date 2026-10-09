import { describe, it, expect, beforeEach, vi } from "vitest";
import { POST_DRAFT_KEY, API_CONTENT_CACHE, tokenStorage } from "./tokens";

describe("tokenStorage.clear", () => {
  beforeEach(() => localStorage.clear());

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
    vi.unstubAllGlobals();
  });
});
