import { describe, expect, it } from "vitest";
import "@/i18n";
import { contactSettingsErrorMessage, maskPhone } from "./contact-settings";

const apiError = (status: number, code: string, detail = "texte serveur") => ({ response: { status, data: { detail, code } } });

describe("contactSettingsErrorMessage", () => {
  it.each([
    ["contact_phone_unverified", 409, "Vérifiez d'abord votre numéro."],
    ["consent_version_mismatch", 400, "Le texte a changé, relisez-le avant d'accepter."],
    ["consent_text_required", 400, "Lisez et acceptez"],
    ["login_phone_unverified", 409, "Vérifiez d'abord votre numéro de connexion."],
    ["phone_invalid", 400, "n'est pas valide"],
    ["otp_invalid", 400, "Code incorrect"],
    ["otp_expired", 400, "expiré"],
    ["otp_attempts_exceeded", 429, "Trop d'essais"],
    ["contact_phone_missing", 404, "Enregistrez d'abord"],
    ["channel_unknown", 404, "n'existe pas"],
  ])("%s donne un message français", (code, status, expected) => {
    expect(contactSettingsErrorMessage(apiError(status, code))).toContain(expected);
  });

  it("code inconnu : détail du serveur ; sans réponse : message générique", () => {
    expect(contactSettingsErrorMessage(apiError(400, "autre", "Détail serveur"))).toBe("Détail serveur");
    expect(contactSettingsErrorMessage(new Error("réseau"))).toContain("n'a pas abouti");
  });
});

describe("maskPhone", () => {
  it("ne garde que les 4 derniers chiffres", () => {
    expect(maskPhone("+243812345678")).toBe("+243 ••• ••• 5678");
    expect(maskPhone("+243812345678")).not.toContain("8123");
  });
  it("vide sans numéro", () => {
    expect(maskPhone(undefined)).toBe("");
    expect(maskPhone("12")).toBe("");
  });
});
