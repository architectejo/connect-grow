import { describe, expect, it } from "vitest";
import "@/i18n";
import { classifyCreateInvitationError, classifyInvitationError, clearsTokenOnFailure, isInvitationExpired } from "./invitations";
import { describeApiError } from "./api-errors";

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
      message: expect.stringContaining("nombre maximal d'invitations en attente"),
    });
  });
  it("429 avec Retry-After : délai en minutes ; sans : message simple", () => {
    expect(classifyCreateInvitationError(apiError(429, undefined, {}, { "retry-after": "600" }))).toMatchObject({ kind: "rate", retryAfter: 600, message: expect.stringContaining("10 min") });
    expect(classifyCreateInvitationError(apiError(429))).toMatchObject({ kind: "rate", message: "Vous avez créé beaucoup d'invitations. Réessayez plus tard." });
  });
  it("400 de champ : étiquette sous le champ, rôle (ou invitation_role_not_allowed) sous les rôles", () => {
    expect(classifyCreateInvitationError(apiError(400, undefined, { label: ["Trop long."] }))).toMatchObject({ kind: "field", field: "label", message: "Trop long." });
    expect(classifyCreateInvitationError(apiError(400, undefined, { role: ["Invalide."] }))).toMatchObject({ kind: "field", field: "role", message: "Ce rôle ne peut pas être donné par invitation." });
    expect(classifyCreateInvitationError(apiError(400, "invitation_role_not_allowed"))).toMatchObject({ kind: "field", field: "role" });
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
    ["409 organization_limit_reached", apiError(409, "organization_limit_reached"), "limit"],
    ["409 already_member", apiError(409, "already_member"), "member"],
    ["403 DENY_SECURITY", apiError(403, "DENY_SECURITY"), "security"],
    ["401", apiError(401), "unauthenticated"],
    ["429", apiError(429), "rate"],
    ["réseau coupé", NETWORK, "network"],
    ["500", apiError(500), "generic"],
  ])("%s -> %s", (_label, error, kind) => {
    expect(classifyInvitationError(error).kind).toBe(kind);
  });

  it("429 : lit Retry-After", () => {
    expect(classifyInvitationError(apiError(429, undefined, {}, { "retry-after": "120" }))).toEqual({ kind: "rate", retryAfter: 120 });
  });

  it("le jeton est supprimé sur invalid et member seulement (conservé sur les autres)", () => {
    expect(clearsTokenOnFailure("invalid")).toBe(true);
    expect(clearsTokenOnFailure("member")).toBe(true);
    for (const kind of ["phone", "limit", "rate", "network", "unauthenticated", "security", "generic"] as const) expect(clearsTokenOnFailure(kind), kind).toBe(false);
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
    ["invitation_limit_reached", "Le nombre maximal d'invitations en attente est atteint."],
    ["invitation_role_not_allowed", "Ce rôle ne peut pas être donné par invitation."],
    ["already_member", "Vous faites déjà partie de cette organisation."],
  ])("%s a un texte dédié", (code, text) => {
    expect(describeApiError(apiError(409, code))).toContain(text);
  });
});
