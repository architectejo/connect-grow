import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { apiErrorMessage, httpStatus, isRateLimited, rateLimitMessage, retryAfterSeconds, shouldRetryQuery } from "./errors";

const failure = (status: number, data: unknown = {}, headers: Record<string, string> = {}) => ({ response: { status, data, headers } });

describe("retryAfterSeconds", () => {
  it("lit l'en-tête Retry-After en secondes", () => {
    expect(retryAfterSeconds(failure(429, {}, { "retry-after": "42" }))).toBe(42);
  });

  it("accepte l'en-tête sous sa casse d'origine", () => {
    expect(retryAfterSeconds(failure(429, {}, { "Retry-After": "7" }))).toBe(7);
  });

  it("lit un objet d'en-têtes de type AxiosHeaders (méthode get)", () => {
    const headers = { get: (name: string) => (name.toLowerCase() === "retry-after" ? "15" : undefined) };
    expect(retryAfterSeconds({ response: { status: 429, data: {}, headers } })).toBe(15);
  });

  it("lit une date HTTP", () => {
    const now = Date.parse("2026-10-09T12:00:00Z");
    expect(retryAfterSeconds(failure(429, {}, { "retry-after": "Fri, 09 Oct 2026 12:00:30 GMT" }), now)).toBe(30);
  });

  it("se rabat sur le délai cité dans le corps DRF quand l'en-tête est masqué (CORS)", () => {
    expect(retryAfterSeconds(failure(429, { detail: "Request was throttled. Expected available in 58 seconds." }))).toBe(58);
  });

  it("renvoie undefined sans information", () => {
    expect(retryAfterSeconds(failure(429))).toBeUndefined();
    expect(retryAfterSeconds(new Error("réseau"))).toBeUndefined();
  });

  it("ne renvoie jamais moins d'une seconde", () => {
    expect(retryAfterSeconds(failure(429, {}, { "retry-after": "0" }))).toBe(1);
  });
});

describe("rateLimitMessage", () => {
  it("affiche le délai en français, au pluriel", () => {
    expect(rateLimitMessage(failure(429, {}, { "retry-after": "42" }))).toBe("Trop de tentatives, réessayez dans 42 secondes.");
  });

  it("accorde le singulier", () => {
    expect(rateLimitMessage(failure(429, {}, { "retry-after": "1" }))).toBe("Trop de tentatives, réessayez dans 1 seconde.");
  });

  it("reste lisible sans délai connu", () => {
    expect(rateLimitMessage(failure(429))).toBe(i18n.t("errors.tooManyAttemptsNoDelay"));
  });
});

describe("apiErrorMessage", () => {
  it("donne le message de délai pour un 429, jamais le texte anglais de DRF", () => {
    const message = apiErrorMessage(failure(429, { detail: "Request was throttled. Expected available in 9 seconds." }, { "retry-after": "9" }));
    expect(message).toBe("Trop de tentatives, réessayez dans 9 secondes.");
  });

  it("renvoie le premier message d'un champ", () => {
    expect(apiErrorMessage(failure(400, { post: ["Cette annonce n'est plus disponible."] }))).toBe("Cette annonce n'est plus disponible.");
  });

  it("préfère la clé error (409 réponse déjà écrite, 403 avis masqué)", () => {
    expect(apiErrorMessage(failure(409, { error: "Une réponse existe déjà." }))).toBe("Une réponse existe déjà.");
    expect(apiErrorMessage(failure(403, { detail: "Cet avis a été masqué." }))).toBe("Cet avis a été masqué.");
  });

  it("traduit le 404 d'une action sur l'offre d'autrui, mais garde un message métier explicite", () => {
    expect(apiErrorMessage(failure(404, { detail: "Pas trouvé." }))).toBe(i18n.t("errors.notFound"));
    expect(apiErrorMessage(failure(404, { error: "Photo introuvable." }))).toBe("Photo introuvable.");
  });

  it("n'affiche jamais le corps d'une erreur 5xx", () => {
    expect(apiErrorMessage(failure(500, "<html>Traceback (most recent call last)</html>"))).toBe(i18n.t("errors.server"));
    expect(apiErrorMessage(failure(502, { detail: "secret interne" }))).toBe(i18n.t("errors.server"));
  });

  it("limite la longueur du message affiché à 200 caractères", () => {
    const message = apiErrorMessage(failure(400, { error: "x".repeat(500) }));
    expect(message).toHaveLength(200);
    expect(message.endsWith("…")).toBe(true);
  });

  it("utilise le texte de repli sans réponse du serveur", () => {
    expect(apiErrorMessage(new Error("réseau"), "Échec.")).toBe("Échec.");
    expect(apiErrorMessage(new Error("réseau"))).toBe(i18n.t("errors.generic"));
  });
});

describe("statut et relance", () => {
  it("expose le code HTTP", () => {
    expect(httpStatus(failure(429))).toBe(429);
    expect(httpStatus(new Error("x"))).toBeUndefined();
    expect(isRateLimited(failure(429))).toBe(true);
    expect(isRateLimited(failure(400))).toBe(false);
  });

  it("ne relance jamais automatiquement un 4xx (dont 429)", () => {
    expect(shouldRetryQuery(0, failure(429))).toBe(false);
    expect(shouldRetryQuery(0, failure(404))).toBe(false);
  });

  it("relance une fois une panne réseau ou serveur", () => {
    expect(shouldRetryQuery(0, new Error("réseau"))).toBe(true);
    expect(shouldRetryQuery(0, failure(503))).toBe(true);
    expect(shouldRetryQuery(1, failure(503))).toBe(false);
  });
});
