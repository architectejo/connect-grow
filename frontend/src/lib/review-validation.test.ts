import { describe, expect, it } from "vitest";
import { isReviewDraftValid, isValidRating, isValidReviewComment, reviewCommentLength, toReviewInput } from "./review-validation";

describe("validation d'un avis", () => {
  it("compte le commentaire sans les espaces de début et de fin", () => {
    expect(reviewCommentLength("  abc  ")).toBe(3);
  });

  it("accepte un commentaire de 10 à 500 caractères", () => {
    expect(isValidReviewComment("a".repeat(9))).toBe(false);
    expect(isValidReviewComment("a".repeat(10))).toBe(true);
    expect(isValidReviewComment("a".repeat(500))).toBe(true);
    expect(isValidReviewComment("a".repeat(501))).toBe(false);
    expect(isValidReviewComment(`   ${"a".repeat(9)}   `)).toBe(false);
  });

  it("n'accepte que des notes entières de 1 à 5", () => {
    expect([0, 1, 3, 5, 6, 3.5].map(isValidRating)).toEqual([false, true, true, true, false, false]);
  });

  it("exige les deux notes et un commentaire valide", () => {
    const base = { offer_rating: 4, seller_rating: 5, content: "Très bon contact." };
    expect(isReviewDraftValid(base)).toBe(true);
    expect(isReviewDraftValid({ ...base, offer_rating: 0 })).toBe(false);
    expect(isReviewDraftValid({ ...base, seller_rating: 0 })).toBe(false);
    expect(isReviewDraftValid({ ...base, content: "court" })).toBe(false);
  });

  it("envoie le commentaire nettoyé et rien d'autre", () => {
    expect(toReviewInput({ offer_rating: 4, seller_rating: 5, content: "  Très bon contact.  " })).toEqual({
      offer_rating: 4,
      seller_rating: 5,
      content: "Très bon contact.",
    });
  });
});
