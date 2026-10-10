import type { Post, PostBadge, Seller } from "@/api/types";

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

/** Vendeur dont la vérification a été validée (badge « Vérifié », jamais déduit d'une note). */
export function isSellerVerified(seller?: Partial<Seller> | null): boolean {
  return !!seller?.business_profile?.is_verified;
}
