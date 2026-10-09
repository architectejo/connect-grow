import type { Post, PostBadge, Seller } from "@/api/types";

/** Cahier des charges 3.7 : le score n'est public qu'à partir de 3 avis. */
export const TRUST_MIN_REVIEWS = 3;
/** Cahier des charges 3.8 : « Vendeur fiable » = Trust Score ≥ 4,5 avec au moins 10 avis. */
export const RELIABLE_MIN_SCORE = 4.5;
export const RELIABLE_MIN_REVIEWS = 10;

export interface TrustInfo {
  /** Score affichable, ou null si « Nouveau vendeur ». */
  score: number | null;
  reviewsCount?: number;
  isNew: boolean;
  isReliable: boolean;
  isVerified: boolean;
}

export function getSellerTrust(seller?: Partial<Seller> | null): TrustInfo {
  const reviewsCount = seller?.reviews_count;
  // Le back-end calcule le Trust Score bayésien et le masque (null) sous 3 avis.
  // Repli sur l'ancienne moyenne brute si l'API ne renvoie pas encore ces champs.
  const hasBackendScore = seller?.trust_score !== undefined || seller?.is_new_seller !== undefined;
  const rawScore = hasBackendScore ? seller?.trust_score ?? null : seller?.avg_rating || null;
  const isNew =
    seller?.is_new_seller ?? (reviewsCount !== undefined ? reviewsCount < TRUST_MIN_REVIEWS : rawScore === null);
  const score = isNew ? null : rawScore;
  const isReliable =
    seller?.is_trusted_seller ??
    (score !== null && reviewsCount !== undefined && reviewsCount >= RELIABLE_MIN_REVIEWS && score >= RELIABLE_MIN_SCORE);

  return {
    score,
    reviewsCount,
    isNew,
    isReliable,
    isVerified: !!seller?.business_profile?.is_verified,
  };
}

/** Badges d'une annonce, dans l'ordre d'affichage. */
export function getPostBadges(post: Post): PostBadge[] {
  if (post.badges) return post.badges;
  const badges: PostBadge[] = [];
  if (post.is_sponsored) badges.push("sponsored");
  // Repli sur le rang « Elite » si l'API ne renvoie pas encore is_trending
  if (post.is_trending ?? post.visibility_rank === "Elite") badges.push("trending");
  return badges;
}

/** Nom public du vendeur : nom de la boutique pour un profil Business. */
export function sellerDisplayName(seller?: Partial<Seller> | null): string {
  return seller?.business_profile?.business_name || seller?.full_name || "Vendeur";
}
