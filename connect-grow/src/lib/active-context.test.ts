import { beforeEach, describe, expect, it } from "vitest";
import type { AvailableContext } from "@/api/types";
import fixture from "@/api/__fixtures__/contexts.json";
import {
  activeContextHeader,
  activeContextStore,
  isContextDependentQuery,
  reconcileSelection,
  toSelection,
} from "./active-context";
import { ACTIVE_CONTEXT_KEY, tokenStorage } from "./tokens";

const contexts = fixture.response.results as AvailableContext[];
const [personal, provider, shop, collective] = contexts;
const USER_ID = personal.id;

beforeEach(() => {
  localStorage.clear();
  activeContextStore._resetForTests();
});

describe("contrat de contexts/ (fixture)", () => {
  it("chaque élément porte exactement les 8 clés du contrat", () => {
    for (const item of contexts) {
      expect(Object.keys(item).sort()).toEqual(
        ["capabilities", "id", "migrated_from_business", "name", "org_type", "photo", "role", "type"].sort(),
      );
    }
  });
});

describe("mémorisation du profil actif", () => {
  it("écrit nom, type et identifiant, liés à l'identifiant du compte", () => {
    activeContextStore.set(toSelection(USER_ID, shop));
    const stored = JSON.parse(localStorage.getItem(ACTIVE_CONTEXT_KEY) as string);
    expect(stored).toEqual({ userId: USER_ID, type: "ORGANIZATION", id: shop.id, name: shop.name, role: "ADMIN", orgType: "BOUTIQUE" });
  });

  it("ne mémorise aucune donnée sensible : ni capacités, ni photo, ni contact, ni jeton", () => {
    activeContextStore.set({ ...toSelection(USER_ID, shop)!, ...({ capabilities: ["x"], photo: "http://x", phone: "+243000", email: "a@b.c", access: "jwt" } as object) });
    const raw = localStorage.getItem(ACTIVE_CONTEXT_KEY) as string;
    for (const forbidden of ["capabilities", "photo", "phone", "email", "access", "jwt", "http"]) expect(raw).not.toContain(forbidden);
    expect(Object.keys(JSON.parse(raw)).sort()).toEqual(["id", "name", "orgType", "role", "type", "userId"]);
  });

  it("le profil personnel n'est pas mémorisé : l'absence de valeur désigne le personnel", () => {
    activeContextStore.set(toSelection(USER_ID, shop));
    activeContextStore.set(toSelection(USER_ID, personal));
    expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).toBeNull();
    expect(activeContextHeader()).toBeUndefined();
  });

  it("relit la valeur mémorisée au démarrage et produit l'en-tête", () => {
    activeContextStore.set(toSelection(USER_ID, provider));
    activeContextStore._resetForTests(); // nouvel onglet ou rechargement
    expect(activeContextStore.get()?.id).toBe(provider.id);
    expect(activeContextHeader()).toBe(`PROVIDER:${provider.id}`);
  });

  it("ignore et supprime une valeur corrompue ou falsifiée", () => {
    for (const bad of ["pas du json", JSON.stringify({ userId: "u", type: "USER", id: "x", name: "n" }), JSON.stringify({ userId: "u", type: "ORGANIZATION", id: "pas-un-uuid", name: "n" })]) {
      localStorage.setItem(ACTIVE_CONTEXT_KEY, bad);
      activeContextStore._resetForTests();
      expect(activeContextStore.get()).toBeNull();
      expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).toBeNull();
    }
  });

  it("est purgée à la déconnexion (tokenStorage.clear)", () => {
    tokenStorage.set("acces", "refresh");
    activeContextStore.set(toSelection(USER_ID, shop));
    tokenStorage.clear();
    expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).toBeNull();
  });

  it("reset() efface la mémoire et le stockage, et prévient les abonnés", () => {
    activeContextStore.set(toSelection(USER_ID, shop));
    let calls = 0;
    activeContextStore.subscribe(() => calls++);
    activeContextStore.reset();
    expect(activeContextStore.get()).toBeNull();
    expect(localStorage.getItem(ACTIVE_CONTEXT_KEY)).toBeNull();
    expect(calls).toBe(1);
  });
});

describe("validation contre contexts/ (le serveur fait foi)", () => {
  it("aucune sélection : profil personnel", () => {
    expect(reconcileSelection(null, USER_ID, contexts)).toEqual({ kind: "personal" });
  });

  it("profil présent : conservé, nom et rôle rafraîchis", () => {
    const stale = { ...toSelection(USER_ID, shop)!, name: "Ancien nom", role: "OWNER" as const };
    const result = reconcileSelection(stale, USER_ID, contexts);
    expect(result).toMatchObject({ kind: "keep", selection: { id: shop.id, name: "Boutique Test", role: "ADMIN" } });
  });

  it("profil absent de la liste : perdu, avec son nom (jamais de repli silencieux)", () => {
    const withoutShop = contexts.filter((c) => c.id !== shop.id);
    expect(reconcileSelection(toSelection(USER_ID, shop), USER_ID, withoutShop)).toEqual({ kind: "lost", lostName: "Boutique Test" });
  });

  it("profil mémorisé par un autre compte : ignoré", () => {
    expect(reconcileSelection(toSelection("autre-compte", shop), USER_ID, contexts)).toEqual({ kind: "personal" });
  });

  it("un prestataire désactivé disparaît de la liste : perdu", () => {
    const withoutProvider = contexts.filter((c) => c.type !== "PROVIDER");
    expect(reconcileSelection(toSelection(USER_ID, provider), USER_ID, withoutProvider).kind).toBe("lost");
  });
});

describe("requêtes dépendantes du profil", () => {
  it.each([
    [["account", "dashboard"]],
    [["account", "trash"]],
    [["account", "contact-settings"]],
    [["marketplace", "my-posts"]],
    [["messages", "conversations"]],
    [["messages", "thread", "c1"]],
    [["interactions", "reveals-received", "all"]],
  ])("%j est réinitialisée au changement de profil", (key) => {
    expect(isContextDependentQuery(key)).toBe(true);
  });

  it.each([
    [["account", "favorites"]],
    [["account", "notifications"]],
    [["account", "kyc"]],
    [["marketplace", "posts", {}, null]],
    [["marketplace", "post", "p1"]],
    [["accounts", "me"]],
    [["contexts", "u1"]],
    [["config", "features"]],
  ])("%j reste en cache (toujours personnel ou public)", (key) => {
    expect(isContextDependentQuery(key)).toBe(false);
  });

  it("collective : rôle analyste sans capacité de publication", () => {
    expect(collective.capabilities).not.toContain("offer.publish");
  });
});
