import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import "@/i18n";
import fr from "@/i18n/locales/fr";
import { describeApiError } from "./api-errors";
import { ORGANIZATION_ROLES, assignableRoles, classifyTeamError, invitableRoles, isOwnersOnlyRow, memberActions, needsReauthentication, roleRequiresConfirmation, scopeLabel } from "./team";

const failure = (status: number, data: unknown = {}, headers: Record<string, string> = {}) =>
  new AxiosError(`HTTP ${status}`, String(status), undefined, null, { status, data, headers } as unknown as AxiosResponse);
const coded = (status: number, code: string) => failure(status, { detail: "Message serveur à ne pas afficher", code });
const noResponse = () => new AxiosError("Network Error", "ERR_NETWORK");

const MANAGE = ["org.view_internal", "org.manage_members", "org.manage_roles"];
const owner = { role: "OWNER" as const, capabilities: MANAGE };
const admin = { role: "ADMIN" as const, capabilities: MANAGE };
const editor = { role: "EDITOR" as const, capabilities: ["org.view_internal"] };

describe("memberActions : menu selon le rôle de l'acteur et de la cible", () => {
  it("un administrateur principal : changer le rôle et transférer sur tous, retirer sauf sur un administrateur principal", () => {
    expect(memberActions(owner, { role: "OWNER", is_self: false })).toEqual(["changeRole", "transfer"]);
    for (const role of ["ADMIN", "EDITOR", "ANALYST", "MEMBER"] as const) {
      expect(memberActions(owner, { role, is_self: false })).toEqual(["changeRole", "transfer", "remove"]);
    }
  });
  it("jamais de menu sur sa propre ligne, quel que soit le rôle", () => {
    expect(memberActions(owner, { role: "OWNER", is_self: true })).toEqual([]);
    expect(memberActions(admin, { role: "ADMIN", is_self: true })).toEqual([]);
  });
  it("un administrateur : changer le rôle et retirer, jamais de transfert, rien sur un administrateur principal", () => {
    expect(memberActions(admin, { role: "EDITOR", is_self: false })).toEqual(["changeRole", "remove"]);
    expect(memberActions(admin, { role: "MEMBER", is_self: false })).toEqual(["changeRole", "remove"]);
    expect(memberActions(admin, { role: "ADMIN", is_self: false })).toEqual(["changeRole", "remove"]);
    expect(memberActions(admin, { role: "OWNER", is_self: false })).toEqual([]);
  });
  it("éditeur, analyste et membre : aucune action, sur aucun rôle", () => {
    for (const role of ORGANIZATION_ROLES) {
      expect(memberActions(editor, { role, is_self: false })).toEqual([]);
      expect(memberActions({ role: "ANALYST", capabilities: [] }, { role, is_self: false })).toEqual([]);
      // Capacités de MEMBER (contrat §7.1) : org.leave et org.view_internal seulement
      expect(memberActions({ role: "MEMBER", capabilities: ["org.leave", "org.view_internal"] }, { role, is_self: false })).toEqual([]);
      expect(isOwnersOnlyRow({ role: "MEMBER", capabilities: [] }, { role, is_self: false })).toBe(false);
    }
  });
  it("suit les capacités : sans org.manage_roles, ni changement de rôle ni transfert", () => {
    const limited = { role: "OWNER" as const, capabilities: ["org.manage_members"] };
    expect(memberActions(limited, { role: "EDITOR", is_self: false })).toEqual(["remove"]);
  });
  it("« Réservé aux administrateurs principaux » seulement pour un administrateur devant un administrateur principal", () => {
    expect(isOwnersOnlyRow(admin, { role: "OWNER", is_self: false })).toBe(true);
    expect(isOwnersOnlyRow(admin, { role: "EDITOR", is_self: false })).toBe(false);
    expect(isOwnersOnlyRow(owner, { role: "OWNER", is_self: false })).toBe(false);
  });
});

describe("rôles attribuables et ressaisie du mot de passe", () => {
  it("ordre des rôles : Membre en dernier (contrat §7.1)", () => {
    expect(ORGANIZATION_ROLES).toEqual(["OWNER", "ADMIN", "EDITOR", "ANALYST", "MEMBER"]);
  });
  it("un administrateur n'attribue jamais Administrateur principal ; Membre est attribuable", () => {
    expect(assignableRoles("OWNER")).toEqual(["OWNER", "ADMIN", "EDITOR", "ANALYST", "MEMBER"]);
    expect(assignableRoles("ADMIN")).toEqual(["ADMIN", "EDITOR", "ANALYST", "MEMBER"]);
  });
  it("exigée pour une promotion vers Administrateur principal ou la rétrogradation d'un Administrateur principal seulement", () => {
    expect(needsReauthentication("ADMIN", "OWNER")).toBe(true);
    expect(needsReauthentication("OWNER", "ADMIN")).toBe(true);
    expect(needsReauthentication("ADMIN", "EDITOR")).toBe(false);
    expect(needsReauthentication("EDITOR", "ANALYST")).toBe(false);
    expect(needsReauthentication("OWNER", "OWNER")).toBe(false);
    expect(needsReauthentication("ANALYST", "MEMBER")).toBe(false);
    expect(needsReauthentication("OWNER", "MEMBER")).toBe(true);
  });
});

describe("scopeLabel : périmètre affiché, jamais choisi (spec D2 §2.4)", () => {
  const t = (key: string) => key;
  it("ORGANIZATION : « Toute l'organisation »", () => {
    expect(scopeLabel({ type: "ORGANIZATION" }, t)).toBe("scope.ORGANIZATION");
    expect(fr.scope.ORGANIZATION).toBe("Toute l'organisation");
  });
  it("toute autre valeur (inatteignable en V1) : « Périmètre limité », sans détail inventé", () => {
    expect(scopeLabel({ type: "CITY" }, t)).toBe("scope.limited");
    expect(scopeLabel({ type: "UNIT" }, t)).toBe("scope.limited");
    expect(fr.scope.limited).toBe("Périmètre limité");
  });
});

describe("textes des codes d'erreur d'équipe (describeApiError)", () => {
  it.each([
    ["last_effective_owner", 409, fr.errors.code.last_effective_owner],
    ["owner_must_be_demoted", 409, fr.errors.code.owner_must_be_demoted],
    ["reauthentication_failed", 403, fr.errors.code.reauthentication_failed],
    ["member_not_found", 404, fr.errors.code.member_not_found],
    ["user_unavailable", 400, fr.errors.code.user_unavailable],
    ["invalid_transfer", 400, fr.errors.code.invalid_transfer],
    ["use_leave", 400, fr.errors.code.use_leave],
    ["confirmation_required", 400, fr.errors.code.confirmation_required],
    ["password_required", 400, fr.errors.code.password_required],
  ])("%s : texte i18n, jamais le detail du serveur", (code, status, expected) => {
    const text = describeApiError(coded(status, code));
    expect(text).toBe(expected);
    expect(text).not.toContain("serveur");
  });
  it("last_owner en retrait ou rétrogradation : texte « au moins un administrateur principal »", () => {
    expect(describeApiError(coded(409, "last_owner"), { demote: true })).toBe(fr.errors.code.last_owner_demote);
  });
});

describe("classifyTeamError", () => {
  it("403 reauthentication_failed : erreur de champ mot de passe", () => {
    expect(classifyTeamError(coded(403, "reauthentication_failed"))).toEqual({ kind: "reauth", message: "Mot de passe incorrect." });
  });
  it("404 member_not_found : le membre n'est plus là", () => {
    expect(classifyTeamError(coded(404, "member_not_found"))).toMatchObject({ kind: "gone", message: fr.team.alreadyGone });
  });
  it("DENY_PERMISSION et DENY_RELATION : refus avec le texte « demandez à un administrateur principal »", () => {
    expect(classifyTeamError(coded(403, "DENY_PERMISSION"))).toEqual({ kind: "denied", message: fr.errors.deny.PERMISSION.org });
    expect(classifyTeamError(coded(403, "DENY_RELATION"))).toMatchObject({ kind: "denied" });
  });
  it("429 : bouton à désactiver, délai lu dans Retry-After", () => {
    expect(classifyTeamError(failure(429, {}, { "retry-after": "90" }))).toEqual({ kind: "rate", message: fr.team.retryLater, retryAfter: 90 });
    expect(classifyTeamError(failure(429))).toMatchObject({ kind: "rate", retryAfter: undefined });
  });
  it("réseau coupé : message de connexion perdue, rien n'est mis en file", () => {
    expect(classifyTeamError(noResponse())).toEqual({ kind: "form", message: fr.team.networkLost });
  });
  it("erreur de champ DRF sur le rôle", () => {
    expect(classifyTeamError(failure(400, { role: ["« X » n'est pas un choix valide."] }))).toMatchObject({ kind: "field", field: "role" });
    expect(classifyTeamError(failure(400, { my_new_role: ["Choix invalide."] }))).toMatchObject({ kind: "field", field: "my_new_role" });
  });
  it.each([
    ["last_owner", 409, fr.errors.code.last_owner_demote],
    ["last_effective_owner", 409, fr.errors.code.last_effective_owner],
    ["owner_must_be_demoted", 409, fr.errors.code.owner_must_be_demoted],
    ["user_unavailable", 400, fr.errors.code.user_unavailable],
    ["invalid_transfer", 400, fr.errors.code.invalid_transfer],
    ["use_leave", 400, fr.errors.code.use_leave],
    ["confirmation_required", 400, fr.errors.code.confirmation_required],
    ["password_required", 400, fr.errors.code.password_required],
  ])("%s : message dans la fenêtre", (code, status, message) => {
    expect(classifyTeamError(coded(status, code))).toEqual({ kind: "form", message });
  });
  it("DENY_SECURITY et DENY_OBJECT_STATE : textes existants, fenêtre conservée", () => {
    expect(classifyTeamError(coded(403, "DENY_SECURITY"))).toEqual({ kind: "form", message: fr.errors.deny.SECURITY.action });
    expect(classifyTeamError(coded(403, "DENY_OBJECT_STATE"))).toEqual({ kind: "form", message: fr.errors.deny.OBJECT_STATE.action });
  });
});

describe("invitableRoles (spec D2 §7.1, L1-01-F2bis)", () => {
  it("administrateur principal et administrateur : Membre, Analyste, Éditeur, Administrateur ; jamais Administrateur principal", () => {
    expect(invitableRoles("OWNER")).toEqual(["MEMBER", "ANALYST", "EDITOR", "ADMIN"]);
    expect(invitableRoles("ADMIN")).toEqual(["MEMBER", "ANALYST", "EDITOR", "ADMIN"]);
    for (const role of ORGANIZATION_ROLES) expect(invitableRoles(role)).not.toContain("OWNER");
  });
  it("éditeur, analyste, membre : aucun rôle (bouton Inviter absent)", () => {
    expect(invitableRoles("EDITOR")).toEqual([]);
    expect(invitableRoles("ANALYST")).toEqual([]);
    expect(invitableRoles("MEMBER")).toEqual([]);
  });
  it("seul Administrateur demande une confirmation par code", () => {
    expect(roleRequiresConfirmation("ADMIN")).toBe(true);
    for (const role of ["EDITOR", "ANALYST", "MEMBER"] as const) expect(roleRequiresConfirmation(role)).toBe(false);
  });
});
