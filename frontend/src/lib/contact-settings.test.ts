import { describe, expect, it } from "vitest";
import "@/i18n";
import { availableChannels, contactSettingsErrorMessage, isChannelNotAvailable, maskPhone } from "./contact-settings";

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
    ["account_too_new", 403, "trop récent pour enregistrer un numéro de contact"],
    ["channel_not_available", 400, "n'est pas proposé pour ce profil"],
    ["login_phone_not_allowed", 400, "ne peut pas servir de numéro à l'organisation"],
  ])("%s donne un message français", (code, status, expected) => {
    expect(contactSettingsErrorMessage(apiError(status, code))).toContain(expected);
  });

  it("channel_not_available : reconnu par le code, jamais par le texte du serveur", () => {
    const error = apiError(400, "channel_not_available", "Ce moyen de contact n'est pas disponible pour ce contexte.");
    expect(isChannelNotAvailable(error)).toBe(true);
    expect(contactSettingsErrorMessage(error)).not.toContain("disponible pour ce contexte");
    expect(isChannelNotAvailable(apiError(400, "phone_invalid"))).toBe(false);
  });

  it.each([
    ["DENY_SECURITY", "temporairement impossible"],
    ["DENY_OBJECT_STATE", "n'est plus dans un état"],
    ["DENY_RELATION", "n'avez pas accès"],
  ])("refus %s (organisation suspendue, archivée, quittée) : texte français commun", (code, expected) => {
    expect(contactSettingsErrorMessage(apiError(403, code, "texte serveur"), { inOrganization: true })).toContain(expected);
  });

  it("DENY_PERMISSION dans une organisation : demandez à un administrateur principal", () => {
    expect(contactSettingsErrorMessage(apiError(403, "DENY_PERMISSION"), { inOrganization: true })).toContain("administrateur principal");
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

describe("availableChannels", () => {
  it("suit la réponse du serveur, dans l'ordre Message, Appel, WhatsApp", () => {
    expect(availableChannels({ available_channels: ["WHATSAPP", "MESSAGE"] })).toEqual(["MESSAGE", "WHATSAPP"]);
  });
  it("sans la clé : le message seul", () => {
    expect(availableChannels(undefined)).toEqual(["MESSAGE"]);
    expect(availableChannels({} as never)).toEqual(["MESSAGE"]);
  });
});
