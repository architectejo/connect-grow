import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { safeNext, loginPath } from "./auth-paths";
import {
  INVITATION_PATH,
  INVITATION_TOKEN_KEY,
  buildInvitationLink,
  clearInvitationToken,
  ingestInvitationToken,
  isValidInvitationToken,
  readInvitationToken,
  tokenFromHash,
} from "./invitation-token";

const TOKEN = "aB3-_xYz0123456789abcdefghijklmnopqrstuvw"; // 41 caractères de l'alphabet autorisé

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
    expect(sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBe(TOKEN);
    expect(JSON.stringify({ ...localStorage })).not.toContain(TOKEN);
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain(TOKEN);
    expect(window.location.pathname).toBe(INVITATION_PATH);
    expect(window.history.length).toBe(before);
  });

  it("est idempotent : un second appel (mode strict de React) retrouve le jeton rangé", () => {
    window.history.replaceState(null, "", `/organization-invitation#token=${TOKEN}`);
    ingestInvitationToken();
    expect(ingestInvitationToken()).toBe(TOKEN);
  });

  it("sans fragment, relit sessionStorage (retour après connexion ou inscription)", () => {
    sessionStorage.setItem(INVITATION_TOKEN_KEY, TOKEN);
    window.history.replaceState(null, "", INVITATION_PATH);
    expect(ingestInvitationToken()).toBe(TOKEN);
  });

  it("aucun jeton : null, sans rien écrire", () => {
    expect(ingestInvitationToken()).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("un fragment mal formé est effacé de la barre d'adresse et n'est jamais rangé", () => {
    window.history.replaceState(null, "", "/organization-invitation#token=a%20b%3Cscript");
    expect(ingestInvitationToken()).toBeNull();
    expect(window.location.hash).toBe("");
    expect(sessionStorage.length).toBe(0);
  });

  it("un jeton mal formé déjà rangé n'est pas relu", () => {
    sessionStorage.setItem(INVITATION_TOKEN_KEY, "pas valide !");
    expect(readInvitationToken()).toBeNull();
  });

  it("clearInvitationToken supprime le jeton rangé", () => {
    sessionStorage.setItem(INVITATION_TOKEN_KEY, TOKEN);
    clearInvitationToken();
    expect(sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
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
