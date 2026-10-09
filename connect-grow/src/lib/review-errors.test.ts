import { describe, expect, it } from "vitest";
import "@/i18n";
import { humanizeSeconds, reviewErrorMessage } from "./review-errors";

const apiError = (status: number, data: unknown, headers: Record<string, string> = {}) => ({ response: { status, data, headers } });

describe("reviewErrorMessage", () => {
  it.each([
    [403, "own_offer", "Vous ne pouvez pas noter votre propre annonce."],
    [403, "not_eligible", "Vous pourrez donner votre avis après avoir contacté le vendeur."],
    [409, "already_reviewed", "Vous avez déjà donné votre avis sur cette annonce."],
    [409, "offer_unavailable", "Cette annonce n'accepte plus d'avis."],
    [404, "offer_not_found", "Annonce introuvable."],
    [403, "edit_window_closed", "Le délai pour modifier cet avis est dépassé."],
    [403, "review_locked", "Cet avis est en cours de vérification ou masqué : il ne peut plus être modifié."],
    [409, "already_replied", "Vous avez déjà répondu à cet avis."],
    [403, "contact_rejected", "Votre contact n'a pas été retenu : vous ne pouvez pas donner d'avis sur cette annonce."],
    [409, "review_recently_deleted", "Vous avez récemment supprimé votre avis sur cette annonce : vous pourrez en donner un nouveau plus tard."],
    [403, "review_locked_after_reply", "Le vendeur a répondu à cet avis : il ne peut plus être modifié ni supprimé."],
    [409, "duplicate_report", "Vous avez déjà signalé cet avis."],
    [400, "invalid_reason", "Ce motif de signalement n'est pas valide."],
    [403, "not_seller", "Seul le vendeur concerné peut effectuer cette action."],
  ])("traduit %i %s à partir du code, pas du texte du serveur", (status, code, expected) => {
    expect(reviewErrorMessage(apiError(status, { detail: "Message du serveur", code }))).toBe(expected);
  });

  it("explique qu'il est trop tôt sans afficher le texte du serveur", () => {
    const message = reviewErrorMessage(apiError(403, { detail: "Vous pourrez donner votre avis dans 3 h.", code: "review_too_early" }));
    expect(message).toMatch(/trop tôt/);
    expect(message).not.toMatch(/3 h/);
  });

  it("429 daily_limit avec Retry-After : donne la durée en français", () => {
    const message = reviewErrorMessage(apiError(429, { detail: "Limite atteinte", code: "daily_limit" }, { "retry-after": "7200" }));
    expect(message).toBe("Vous avez atteint la limite d'avis par jour. Réessayez dans 2 heures.");
  });

  it("429 daily_limit sans Retry-After : message de limite quotidienne", () => {
    expect(reviewErrorMessage(apiError(429, { detail: "Limite atteinte", code: "daily_limit" }))).toBe(
      "Vous avez atteint la limite d'avis par jour. Réessayez demain.",
    );
  });

  it("429 throttled : message de débit générique", () => {
    expect(reviewErrorMessage(apiError(429, { detail: "Throttled", code: "throttled" }, { "retry-after": "30" }))).toBe(
      "Trop de tentatives, réessayez dans 30 secondes.",
    );
  });

  it("erreur de champ 400 : premier message DRF", () => {
    expect(reviewErrorMessage(apiError(400, { content: ["Au moins 10 caractères."] }))).toBe("Au moins 10 caractères.");
  });

  it("erreur inconnue : message générique", () => {
    expect(reviewErrorMessage(new Error("Network Error"))).toBe("Une erreur est survenue. Réessayez.");
  });
});

describe("humanizeSeconds", () => {
  it("choisit une unité lisible", () => {
    expect(humanizeSeconds(45)).toBe("45 secondes");
    expect(humanizeSeconds(600)).toBe("10 minutes");
    expect(humanizeSeconds(3 * 3600)).toBe("3 heures");
  });
});
