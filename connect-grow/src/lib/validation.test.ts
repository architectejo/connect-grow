import { describe, expect, it } from "vitest";
import { parseApiErrors } from "./validation";

const failure = (status: number, data: unknown, headers: Record<string, string> = {}) => ({ response: { status, data, headers } });

describe("parseApiErrors", () => {
  it("affiche le délai d'attente pour un 429", () => {
    const { general, fields } = parseApiErrors(failure(429, {}, { "retry-after": "30" }));
    expect(general).toBe("Trop de tentatives, réessayez dans 30 secondes.");
    expect(fields).toEqual({});
  });

  it("ramène les erreurs par champ (commune hors de la ville, image refusée)", () => {
    const { fields } = parseApiErrors(failure(400, { commune: ["Cette commune n'appartient pas à la ville choisie."], photo: ["Image trop grande."] }));
    expect(fields.commune).toBe("Cette commune n'appartient pas à la ville choisie.");
    expect(fields.photo).toBe("Image trop grande.");
  });

  it("aplatit les erreurs du profil entreprise imbriqué", () => {
    const { fields } = parseApiErrors(failure(400, { business_profile: { logo: ["Image trop grande."] } }));
    expect(fields.logo).toBe("Image trop grande.");
  });

  it("remonte les messages généraux (inscription sans e-mail ni téléphone, code invalide)", () => {
    expect(parseApiErrors(failure(400, { non_field_errors: ["Un e-mail ou un numéro de téléphone est obligatoire."] })).general).toBe(
      "Un e-mail ou un numéro de téléphone est obligatoire.",
    );
    expect(parseApiErrors(failure(400, { error: "Code invalide ou expiré." })).general).toBe("Code invalide ou expiré.");
  });

  it("signale l'absence de réponse du serveur", () => {
    expect(parseApiErrors(new Error("réseau")).general).toContain("réseau");
  });
});
