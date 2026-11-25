import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { safeNext, loginPath } from "./auth-paths";
import {
  INVITATION_PATH,
  INVITATION_TOKEN_KEY,
  INVITATION_TOKEN_MAX_AGE_MS,
  bindInvitationToken,
  buildInvitationLink,
  clearInvitationToken,
  ingestInvitationToken,
  isValidInvitationToken,
  readInvitationToken,
  storeInvitationToken,
  tokenFromHash,
} from "./invitation-token";

const TOKEN = "aB3-_xYz0123456789abcdefghijklmnopqrstuvw"; // 41 caractères de l'alphabet autorisé
const OTHER = "zZ9-_otherTokenOtherTokenOtherTokenOther00";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
});
afterEach(() => clearInvitationToken());

describe("forme du jeton et du lien", () => {
  it("accepte l'alphabet A-Za-z0-9_- (1 à 128) et refuse le reste", () => {
    expect(isValidInvitationToken(TOKEN)).toBe(true);
    expect(isValidInvitationToken("a".repeat(128))).toBe(true);
    for (const bad of ["", "a".repeat(129), "abc def", "abc/def", "abc?x=1", "abc#d", "é", null, undefined, 12]) {
      expect(isValidInvitationToken(bad), String(bad)).toBe(false);
    }
  });

  it("le lien de partage place le jeton dans le fragment : jamais en query ni en chemin", () => {
    const link = buildInvitationLink("https://app.example", TOKEN);
    expect(link).toBe(`https://app.example/organization-invitation#token=${TOKEN}`);
    const url = new URL(link);
    expect(url.pathname).toBe("/organization-invitation");
    expect(url.search).toBe("");
    expect(url.hash).toBe(`#token=${TOKEN}`);
  });

  it("lit le jeton d'un fragment conforme, ignore le reste", () => {
    expect(tokenFromHash(`#token=${TOKEN}`)).toBe(TOKEN);
    expect(tokenFromHash(`#a=1&token=${TOKEN}`)).toBe(TOKEN);
    expect(tokenFromHash("")).toBeNull();
    expect(tokenFromHash("#")).toBeNull();
    expect(tokenFromHash("#token=")).toBeNull();
    expect(tokenFromHash("#token=a b")).toBeNull();
    expect(tokenFromHash("#autre=1")).toBeNull();
  });
});

describe("ingestInvitationToken", () => {
  it("range le jeton en sessionStorage (jamais localStorage) et nettoie la barre d'adresse sans nouvelle entrée d'historique", () => {
    window.history.replaceState(null, "", `/organization-invitation#token=${TOKEN}`);
    const before = window.history.length;
    expect(ingestInvitationToken()).toBe(TOKEN);
    expect(readInvitationToken()).toBe(TOKEN);
    expect(sessionStorage.getItem(INVITATION_TOKEN_KEY)).toContain(TOKEN);
    expect(JSON.stringify({ ...localStorage })).not.toContain(TOKEN);
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain(TOKEN);
    expect(window.location.pathname).toBe(INVITATION_PATH);
    expect(window.history.length).toBe(before);
  });

  it("second appel (mode strict) : plus de fragment, le jeton rangé reste lisible", () => {
    window.history.replaceState(null, "", `/organization-invitation#token=${TOKEN}`);
    ingestInvitationToken();
    expect(ingestInvitationToken()).toBeNull();
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("un second lien remplace le premier (et sa liaison à un compte)", () => {
    storeInvitationToken(TOKEN);
    bindInvitationToken("compte-A");
    ingestInvitationToken(`#token=${OTHER}`);
    expect(readInvitationToken("compte-B")).toBe(OTHER);
  });

  it("aucun jeton : null, sans rien écrire", () => {
    expect(ingestInvitationToken()).toBeNull();
    expect(readInvitationToken()).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("un fragment mal formé est effacé de la barre d'adresse et n'est jamais rangé", () => {
    window.history.replaceState(null, "", "/organization-invitation#token=a%20b%3Cscript");
    expect(ingestInvitationToken()).toBeNull();
    expect(window.location.hash).toBe("");
    expect(sessionStorage.length).toBe(0);
  });

  it("un contenu rangé illisible ou mal formé n'est pas relu", () => {
    sessionStorage.setItem(INVITATION_TOKEN_KEY, "pas valide !");
    expect(readInvitationToken()).toBeNull();
    sessionStorage.setItem(INVITATION_TOKEN_KEY, JSON.stringify({ token: "a b", storedAt: Date.now() }));
    expect(readInvitationToken()).toBeNull();
  });

  it("clearInvitationToken supprime le jeton rangé", () => {
    storeInvitationToken(TOKEN);
    clearInvitationToken();
    expect(sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
    expect(readInvitationToken()).toBeNull();
  });
});

describe("protection d'un onglet partagé (audit S2)", () => {
  it("le jeton rangé expire au bout de 60 minutes et il est alors effacé", () => {
    const t0 = Date.parse("2026-11-25T10:00:00Z");
    storeInvitationToken(TOKEN, t0);
    expect(readInvitationToken(undefined, t0 + INVITATION_TOKEN_MAX_AGE_MS)).toBe(TOKEN);
    expect(readInvitationToken(undefined, t0 + INVITATION_TOKEN_MAX_AGE_MS + 1)).toBeNull();
    expect(sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
  });

  it("lié au premier compte : un autre compte ne le lit pas et il est effacé", () => {
    storeInvitationToken(TOKEN);
    bindInvitationToken("compte-A");
    expect(readInvitationToken("compte-A")).toBe(TOKEN);
    bindInvitationToken("compte-B"); // sans effet : déjà lié
    expect(readInvitationToken("compte-B")).toBeNull();
    expect(readInvitationToken("compte-A")).toBeNull();
  });

  it("non lié : lisible par le premier compte connecté", () => {
    storeInvitationToken(TOKEN);
    expect(readInvitationToken("compte-B")).toBe(TOKEN);
  });
});

describe("sessionStorage inaccessible", () => {
  afterEach(() => vi.restoreAllMocks());

  it("écriture refusée : repli mémoire, et l'ancien jeton du stockage est retiré (il ne masque jamais le nouveau)", () => {
    storeInvitationToken(TOKEN);
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    storeInvitationToken(OTHER);
    expect(setItem).toHaveBeenCalled();
    expect(sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
    expect(readInvitationToken()).toBe(OTHER);
    expect(JSON.stringify({ ...localStorage })).not.toContain(OTHER);
  });

  it("lecture et écriture impossibles : le jeton vit en mémoire seulement, puis s'efface", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    storeInvitationToken(TOKEN);
    expect(readInvitationToken()).toBe(TOKEN);
    clearInvitationToken();
    expect(readInvitationToken()).toBeNull();
  });
});

describe("conservation du jeton par ?next=", () => {
  it("safeNext accepte /organization-invitation et la connexion le transmet", () => {
    expect(safeNext("/organization-invitation")).toBe("/organization-invitation");
    expect(loginPath(INVITATION_PATH)).toBe("/login?next=%2Forganization-invitation");
    expect(safeNext(new URLSearchParams(loginPath(INVITATION_PATH).split("?")[1]).get("next"))).toBe("/organization-invitation");
  });
});
