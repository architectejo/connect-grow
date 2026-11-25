import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import "@/i18n";
import fr from "@/i18n/locales/fr";
import { CONTEXT_DENY_CODES, DENY_CODES, describeApiError, isContextDenyCode, isDenyCode, isNetworkError, lostMessageKey, lostReasonFor, organizationDeniedKey } from "./api-errors";

const failure = (status: number, data: unknown = {}, headers: Record<string, string> = {}) =>
  new AxiosError(`HTTP ${status}`, String(status), undefined, null, { status, data, headers } as unknown as AxiosResponse);
const deny = (code: string) => failure(403, { detail: "Message serveur à ne pas afficher", code });

describe("describeApiError : refus DENY_*", () => {
  it.each(CONTEXT_DENY_CODES)("%s : texte « action refusée » issu de fr.ts, jamais le detail du serveur", (code) => {
    const key = code.replace("DENY_", "") as "CONTEXT" | "RELATION" | "SECURITY" | "OBJECT_STATE";
    const text = describeApiError(deny(code));
    expect(text).toBe(fr.errors.deny[key].action);
    expect(text).not.toContain("serveur");
  });

  it("DENY_PERMISSION : texte d'organisation ou générique", () => {
    expect(describeApiError(deny("DENY_PERMISSION"), { inOrganization: true })).toBe(fr.errors.deny.PERMISSION.org);
    expect(describeApiError(deny("DENY_PERMISSION"))).toBe(fr.errors.deny.PERMISSION.generic);
  });

  it("couvre les cinq codes du contrat", () => {
    expect(DENY_CODES).toEqual(["DENY_CONTEXT", "DENY_RELATION", "DENY_PERMISSION", "DENY_SECURITY", "DENY_OBJECT_STATE"]);
    expect(isDenyCode("DENY_RELATION")).toBe(true);
    expect(isDenyCode("DENY_AUTRE")).toBe(false);
    expect(isContextDenyCode("DENY_PERMISSION")).toBe(false); // ne fait jamais perdre le profil
    expect(isContextDenyCode("DENY_SECURITY")).toBe(true);
  });
});

describe("describeApiError : codes métier de l'ADR 0006", () => {
  it.each([
    ["last_owner", 409, fr.errors.code.last_owner],
    ["organization_limit_reached", 409, fr.errors.code.organization_limit_reached],
    ["phone_verification_required", 403, fr.errors.code.phone_verification_required],
    ["name_locked_by_verification", 409, fr.errors.code.name_locked_by_verification],
    ["seller_not_settable", 400, fr.errors.code.seller_not_settable],
  ])("%s", (code, status, expected) => {
    expect(describeApiError(failure(status, { detail: "x", code }))).toBe(expected);
  });

  it("last_owner en rétrogradation", () => {
    expect(describeApiError(failure(409, { code: "last_owner" }), { demote: true })).toBe(fr.errors.code.last_owner_demote);
  });
  it("le plafond d'organisations ne contient aucun chiffre codé en dur", () => {
    expect(fr.errors.code.organization_limit_reached).not.toMatch(/\d/);
  });
});

describe("describeApiError : autres erreurs", () => {
  it("réseau coupé", () => {
    const error = new AxiosError("Network Error");
    expect(isNetworkError(error)).toBe(true);
    expect(describeApiError(error)).toBe(fr.errors.network);
  });
  it("429 avec délai", () => {
    expect(describeApiError(failure(429, {}, { "retry-after": "12" }))).toContain("12");
  });
  it("5xx : texte générique, jamais le corps", () => {
    expect(describeApiError(failure(500, "<html>trace</html>"))).toBe(fr.errors.server);
  });
  it("code inconnu : repli sur la lecture générique", () => {
    expect(describeApiError(failure(400, { detail: "Invalide.", code: "autre" }))).toBe("Invalide.");
  });
});

describe("messages de profil perdu", () => {
  it("un message par raison, tous présents dans fr.ts", () => {
    const lookup = (key: string) => key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], fr);
    for (const reason of ["CONTEXT", "RELATION", "SECURITY", "OBJECT_STATE", "left", "archived"] as const) {
      expect(typeof lookup(lostMessageKey(reason))).toBe("string");
    }
  });
  it("organisation confirmée suspendue ou archivée : textes dédiés, sans motif", () => {
    expect(lostMessageKey("org_suspended")).toBe("errors.lost.suspended");
    expect(lostMessageKey("org_archived")).toBe("errors.lost.archivedByStatus");
    expect(fr.errors.lost.suspended).toContain("suspendue");
    expect(fr.errors.deny.SECURITY.lost).not.toMatch(/suspendue/);
  });
  it("DENY_SECURITY sans entrée dans unavailable : compte limité, pas une suspension", () => {
    const error = failure(403, { detail: "x", code: "DENY_SECURITY" });
    expect(organizationDeniedKey(error)).toBe("org.denied.accountRestricted");
    expect(organizationDeniedKey(failure(403, { detail: "x", code: "DENY_OBJECT_STATE" }))).toBe("org.denied.archived");
    expect(organizationDeniedKey(failure(403, { detail: "x", code: "DENY_RELATION" }))).toBe("org.denied.relation");
  });
  it("code DENY_* vers raison", () => {
    expect(lostReasonFor("DENY_OBJECT_STATE")).toBe("OBJECT_STATE");
    expect(lostReasonFor("DENY_RELATION")).toBe("RELATION");
  });
});
