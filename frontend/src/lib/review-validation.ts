import type { ReviewInput } from "@/api/types";

// CDC v1.2 §3.4 : commentaire de 10 à 500 caractères (espaces de début et de fin retirés avant comptage).
export const REVIEW_MIN_LENGTH = 10;
export const REVIEW_MAX_LENGTH = 500;

export const reviewCommentLength = (text: string) => text.trim().length;

export const isValidReviewComment = (text: string) => {
  const length = reviewCommentLength(text);
  return length >= REVIEW_MIN_LENGTH && length <= REVIEW_MAX_LENGTH;
};

/** Note entière de 1 à 5. */
export const isValidRating = (value: number) => Number.isInteger(value) && value >= 1 && value <= 5;

export interface ReviewDraft {
  offer_rating: number;
  seller_rating: number;
  content: string;
}

export function reviewDraftErrors(draft: ReviewDraft): { ratings: boolean; content: boolean } {
  return {
    ratings: !isValidRating(draft.offer_rating) || !isValidRating(draft.seller_rating),
    content: !isValidReviewComment(draft.content),
  };
}

export function isReviewDraftValid(draft: ReviewDraft): boolean {
  const errors = reviewDraftErrors(draft);
  return !errors.ratings && !errors.content;
}

/** Corps envoyé à l'API : commentaire nettoyé, aucun champ superflu. */
export function toReviewInput(draft: ReviewDraft): ReviewInput {
  return { offer_rating: draft.offer_rating, seller_rating: draft.seller_rating, content: draft.content.trim() };
}
