import { describe, expect, it } from "vitest";
import { DASHBOARD_CAPABILITY, MY_POSTS_CAPABILITY, isPermissionDenied, lacksCapability } from "./dashboard";

const apiError = (status: number, code?: string) => ({ response: { status, data: code ? { detail: "Message du serveur", code } : {}, headers: {} } });
const MEMBER = ["org.leave", "org.view_internal"];

describe("lacksCapability : profil confirmé sans la capacité", () => {
  it("rôle Membre confirmé : ni statistiques ni « Mes annonces » (ADR 0010 §4.1)", () => {
    expect(lacksCapability({ confirmed: true, capabilities: MEMBER }, DASHBOARD_CAPABILITY)).toBe(true);
    expect(lacksCapability({ confirmed: true, capabilities: MEMBER }, MY_POSTS_CAPABILITY)).toBe(true);
  });
  it("analyste confirmé : statistiques et offres en lecture", () => {
    const analyst = ["offer.view_internal", "org.leave", "org.view_internal", "stats.view"];
    expect(lacksCapability({ confirmed: true, capabilities: analyst }, DASHBOARD_CAPABILITY)).toBe(false);
    expect(lacksCapability({ confirmed: true, capabilities: analyst }, MY_POSTS_CAPABILITY)).toBe(false);
  });
  it("profil pas encore confirmé par le serveur : on ne conclut rien (la requête part, le serveur juge)", () => {
    expect(lacksCapability({ confirmed: false, capabilities: [] }, DASHBOARD_CAPABILITY)).toBe(false);
  });
});

describe("isPermissionDenied : 403 DENY_PERMISSION seulement", () => {
  it("reconnaît le refus lié au rôle", () => {
    expect(isPermissionDenied(apiError(403, "DENY_PERMISSION"))).toBe(true);
  });
  it("les autres refus et erreurs restent des erreurs (Réessayer ou flux de profil perdu)", () => {
    expect(isPermissionDenied(apiError(403, "DENY_RELATION"))).toBe(false);
    expect(isPermissionDenied(apiError(403, "DENY_SECURITY"))).toBe(false);
    expect(isPermissionDenied(apiError(403))).toBe(false);
    expect(isPermissionDenied(apiError(500))).toBe(false);
    expect(isPermissionDenied(new Error("réseau"))).toBe(false);
    expect(isPermissionDenied(null)).toBe(false);
  });
});
