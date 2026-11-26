import { describe, expect, it } from "vitest";
import "@/i18n";
import {
  classifyAwaitingActionError,
  classifyConfirmInvitationError,
  classifyCreateInvitationError,
  classifyInvitationError,
  classifyRejectInvitationError,
  clearsTokenOnFailure,
  isInvitationExpired,
} from "./invitations";
import fr from "@/i18n/locales/fr";
import { describeApiError } from "./api-errors";
import { InvitationTokenMissingError } from "./invitation-token";

const apiError = (status: number, code?: string, data: Record<string, unknown> = {}, headers: Record<string, string> = {}) => ({
  isAxiosError: true,
  response: { status, data: code ? { detail: "Message du serveur", code } : data, headers },
});
const NETWORK = { isAxiosError: true, message: "Network Error" };

describe("isInvitationExpired", () => {
  const now = Date.parse("2026-11-10T00:00:00Z");
  it("une invitation en attente et non échue n'est pas expirée", () => {
    expect(isInvitationExpired({ status: "PENDING", expires_at: "2026-11-16T00:00:00Z" }, now)).toBe(false);
  });
  it("EXPIRED, ou PENDING échue, est expirée", () => {
    expect(isInvitationExpired({ status: "EXPIRED", expires_at: "2026-11-16T00:00:00Z" }, now)).toBe(true);
    expect(isInvitationExpired({ status: "PENDING", expires_at: "2026-11-09T00:00:00Z" }, now)).toBe(true);
  });
  it("tout statut autre que PENDING est clos", () => {
    for (const status of ["ACCEPTED", "DECLINED", "REVOKED"] as const) expect(isInvitationExpired({ status, expires_at: "2027-01-01T00:00:00Z" }, now)).toBe(true);
  });
});

describe("classifyCreateInvitationError", () => {
  it("réseau coupé : message qui renvoie à l'onglet Invitations", () => {
    expect(classifyCreateInvitationError(NETWORK)).toMatchObject({ kind: "network", message: expect.stringContaining("Vérifiez l'onglet Invitations") });
  });
  it("409 invitation_limit_reached", () => {
    expect(classifyCreateInvitationError(apiError(409, "invitation_limit_reached"))).toMatchObject({
      kind: "form",
      message: expect.stringContaining("nombre maximal d'invitations ouvertes est atteint (liens en attente et demandes à confirmer)"),
    });
  });
  it("429 avec Retry-After : délai en minutes ; sans : message simple", () => {
    expect(classifyCreateInvitationError(apiError(429, undefined, {}, { "retry-after": "600" }))).toMatchObject({ kind: "rate", retryAfter: 600, message: expect.stringContaining("10 min") });
    expect(classifyCreateInvitationError(apiError(429))).toMatchObject({ kind: "rate", message: "Vous avez créé beaucoup d'invitations. Réessayez plus tard." });
  });
  it("400 de champ : étiquette sous le champ, rôle (ou invitation_role_not_allowed) sous les rôles", () => {
    expect(classifyCreateInvitationError(apiError(400, undefined, { label: ["Trop long."] }))).toMatchObject({ kind: "field", field: "label", message: "Trop long." });
    expect(classifyCreateInvitationError(apiError(400, undefined, { role: ["Invalide."] }))).toMatchObject({ kind: "field", field: "role", message: "Vous ne pouvez pas donner ce rôle par invitation." });
    expect(classifyCreateInvitationError(apiError(400, "invitation_role_not_allowed"))).toMatchObject({ kind: "field", field: "role" });
  });
  it("400 {label} sans message exploitable : texte de la spec « Cette étiquette est trop longue. »", () => {
    expect(classifyCreateInvitationError(apiError(400, undefined, { label: [] }))).toMatchObject({ field: "label", message: "Cette étiquette est trop longue." });
    expect(classifyCreateInvitationError(apiError(400, undefined, { label: [""] }))).toMatchObject({ message: "Cette étiquette est trop longue." });
  });
  it("403 DENY_PERMISSION : refus ; autres DENY : texte existant", () => {
    expect(classifyCreateInvitationError(apiError(403, "DENY_PERMISSION")).kind).toBe("denied");
    expect(classifyCreateInvitationError(apiError(403, "DENY_SECURITY"))).toMatchObject({ kind: "form", message: expect.stringContaining("temporairement impossible") });
  });
});

describe("classifyInvitationError (échange du jeton)", () => {
  it.each([
    ["404 invitation_invalid", apiError(404, "invitation_invalid"), "invalid"],
    ["400 {token}", apiError(400, undefined, { token: ["Requis."] }), "invalid"],
    ["403 phone_verification_required", apiError(403, "phone_verification_required"), "phone"],
    ["409 account_review_required", apiError(409, "account_review_required"), "review"],
    ["409 already_awaiting_confirmation", apiError(409, "already_awaiting_confirmation"), "awaiting"],
    ["409 organization_limit_reached (supprimé du contrat)", apiError(409, "organization_limit_reached"), "generic"],
    ["409 already_member", apiError(409, "already_member"), "member"],
    ["403 DENY_SECURITY", apiError(403, "DENY_SECURITY"), "security"],
    ["401", apiError(401), "unauthenticated"],
    ["429", apiError(429), "rate"],
    ["réseau coupé", NETWORK, "network"],
    ["500", apiError(500), "generic"],
  ])("%s -> %s", (_label, error, kind) => {
    expect(classifyInvitationError(error).kind).toBe(kind);
  });

  it("jeton absent ou inutilisable au moment de l'appel : « missing » (aucun appel n'a eu lieu)", () => {
    expect(classifyInvitationError(new InvitationTokenMissingError()).kind).toBe("missing");
    expect(clearsTokenOnFailure("missing")).toBe(false);
  });

  it("429 : lit Retry-After", () => {
    expect(classifyInvitationError(apiError(429, undefined, {}, { "retry-after": "120" }))).toEqual({ kind: "rate", retryAfter: 120 });
  });

  it("le jeton est supprimé sur invalid et member seulement (conservé sur les autres)", () => {
    expect(clearsTokenOnFailure("invalid")).toBe(true);
    expect(clearsTokenOnFailure("member")).toBe(true);
    for (const kind of ["phone", "review", "awaiting", "rate", "network", "unauthenticated", "security", "generic"] as const) expect(clearsTokenOnFailure(kind), kind).toBe(false);
  });

  it("le résultat ne reprend jamais le message du serveur ni un jeton", () => {
    const failure = classifyInvitationError(apiError(404, "invitation_invalid"));
    expect(JSON.stringify(failure)).not.toContain("Message du serveur");
  });
});

describe("codes d'erreur d'invitation dans describeApiError", () => {
  it.each([
    ["invitation_invalid", "Cette invitation n'est plus valable."],
    ["invitation_not_pending", "Cette invitation n'est plus en attente."],
    ["invitation_not_found", "Cette invitation n'est plus en attente."],
    ["invitation_limit_reached", "Le nombre maximal d'invitations ouvertes est atteint (liens en attente et demandes à confirmer)."],
    ["invitation_role_not_allowed", "Ce rôle ne peut pas être donné par invitation."],
    ["already_member", "Vous faites déjà partie de cette organisation."],
  ])("%s a un texte dédié", (code, text) => {
    expect(describeApiError(apiError(409, code))).toContain(text);
  });
});

describe("classifyConfirmInvitationError (E6g, contrat §7.4.6)", () => {
  it.each([
    ["404 invitation_not_found", apiError(404, "invitation_not_found"), "gone"],
    ["409 invitation_not_awaiting_confirmation", apiError(409, "invitation_not_awaiting_confirmation"), "gone"],
    ["403 DENY_PERMISSION", apiError(403, "DENY_PERMISSION"), "denied"],
    ["400 confirmation_code_required", apiError(400, "confirmation_code_required"), "codeRequired"],
    ["403 reauthentication_failed", apiError(403, "reauthentication_failed"), "reauth"],
    ["400 confirmation_code_invalid", apiError(400, "confirmation_code_invalid"), "codeInvalid"],
    ["409 confirmation_code_exhausted", apiError(409, "confirmation_code_exhausted"), "exhausted"],
    ["400 user_unavailable", apiError(400, "user_unavailable"), "unavailable"],
    ["409 already_member", apiError(409, "already_member"), "alreadyMember"],
    ["400 confirmation_required (inatteignable)", apiError(400, "confirmation_required"), "form"],
    ["400 password_required (inatteignable)", apiError(400, "password_required"), "form"],
    ["403 DENY_SECURITY", apiError(403, "DENY_SECURITY"), "form"],
    ["403 DENY_RELATION", apiError(403, "DENY_RELATION"), "denied"],
    ["409 code non prévu (entitlement)", apiError(409, "team_capacity_reached"), "form"],
    ["429", apiError(429), "rate"],
    ["réseau coupé", NETWORK, "network"],
  ])("%s -> %s", (_label, error, kind) => {
    expect(classifyConfirmInvitationError(error).kind).toBe(kind);
  });

  it("textes de la spec, sans nombre d'essais restants ni message du serveur", () => {
    expect(classifyConfirmInvitationError(apiError(403, "reauthentication_failed"))).toEqual({ kind: "reauth", message: fr.team.confirmInvite.badPassword });
    expect(classifyConfirmInvitationError(apiError(409, "confirmation_code_exhausted"))).toEqual({ kind: "exhausted", message: fr.team.confirmInvite.exhausted });
    expect(classifyConfirmInvitationError(NETWORK)).toEqual({ kind: "network", message: fr.team.confirmInvite.network });
    expect(classifyConfirmInvitationError(apiError(403, "DENY_PERMISSION"))).toEqual({ kind: "denied", message: fr.team.confirmInvite.denied });
    expect(classifyConfirmInvitationError(apiError(429, undefined, {}, { "retry-after": "30" }))).toMatchObject({ kind: "rate", retryAfter: 30 });
    expect(JSON.stringify(classifyConfirmInvitationError(apiError(400, "confirmation_code_invalid")))).not.toMatch(/Message du serveur|\d/);
    expect(fr.team.confirmInvite.codeInvalid + fr.errors.code.confirmation_code_invalid).not.toMatch(/\d/);
  });
});

describe("classifyRejectInvitationError (E6h)", () => {
  it.each([
    ["404 invitation_not_found", apiError(404, "invitation_not_found"), "gone"],
    ["409 invitation_not_awaiting_confirmation", apiError(409, "invitation_not_awaiting_confirmation"), "gone"],
    ["403 DENY_PERMISSION", apiError(403, "DENY_PERMISSION"), "denied"],
    ["403 DENY_RELATION", apiError(403, "DENY_RELATION"), "denied"],
    ["429", apiError(429), "rate"],
    ["réseau coupé", NETWORK, "form"],
  ])("%s -> %s", (_label, error, kind) => {
    expect(classifyRejectInvitationError(error).kind).toBe(kind);
  });
  it("réseau : « Connexion perdue »", () => {
    expect(classifyRejectInvitationError(NETWORK).message).toBe(fr.team.networkLost);
  });
});

describe("classifyAwaitingActionError (E17 : nouveau code, retrait)", () => {
  it("404 / 409 : la demande n'est plus en attente", () => {
    for (const action of ["newCode", "withdraw"] as const) {
      expect(classifyAwaitingActionError(apiError(404, "invitation_not_found"), action)).toEqual({ kind: "gone", message: fr.team.invitations.notPending });
      expect(classifyAwaitingActionError(apiError(409, "invitation_not_awaiting_confirmation"), action).kind).toBe("gone");
      expect(classifyAwaitingActionError(apiError(429), action).kind).toBe("rate");
    }
  });
  it("réseau : texte propre au nouveau code (l'ancien ne fonctionne peut-être plus)", () => {
    expect(classifyAwaitingActionError(NETWORK, "newCode")).toEqual({ kind: "network", message: fr.profiles.awaiting.newCodeNetwork });
    expect(classifyAwaitingActionError(NETWORK, "withdraw")).toEqual({ kind: "network", message: fr.team.networkLost });
  });
});
