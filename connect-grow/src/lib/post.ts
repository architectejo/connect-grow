import type { AvailableContext, Post, PostBadge, Seller, SellerContextType, Uuid } from "@/api/types";
import i18n from "@/i18n";

/** Badges d'une annonce, dans l'ordre d'affichage. */
export function getPostBadges(post: Post): PostBadge[] {
  if (post.badges) return post.badges;
  const badges: PostBadge[] = [];
  if (post.is_sponsored) badges.push("sponsored");
  // Repli sur le rang « Elite » si l'API ne renvoie pas encore is_trending
  if (post.is_trending ?? post.visibility_rank === "Elite") badges.push("trending");
  return badges;
}

/** Nom public du vendeur, tel que fourni par le serveur (« Marie K. » pour un compte personnel ; jamais reconstitué ici). */
export function sellerDisplayName(seller?: Partial<Seller> | null): string {
  return seller?.display_name || i18n.t("seller.anonymous");
}

/** Chemin de la page publique d'un vendeur : `/seller/<user|provider|organization>/<id>`. */
export function sellerPath(contextType: SellerContextType, contextId: Uuid): string {
  return `/seller/${contextType.toLowerCase()}/${contextId}`;
}

/** Chemin de la page publique du vendeur d'une offre. */
export function sellerPathOf(seller: Pick<Seller, "context_type" | "context_id">): string {
  return sellerPath(seller.context_type, seller.context_id);
}

export interface OfferAccess {
  /** Le demandeur peut modifier cette offre (`offer.edit` dans le profil vendeur de l'offre). */
  canEdit: boolean;
  /** Le demandeur est membre actif de l'organisation vendeuse (ou titulaire du profil vendeur) : il ne se contacte pas lui-même. */
  isMember: boolean;
}

/**
 * Droits du demandeur sur une offre, déduits de la liste `contexts/` du serveur (identifiant du profil vendeur de
 * l'offre et capacités de ce profil). `is_owner` de la réponse prime s'il est fourni ; le backend (vérifié le 24/10/2026,
 * fixtures `backend-identity.json`) ne le renvoie toujours pas : ce repli reste donc nécessaire (ADR 0006 §9.6). Le serveur reste le juge : ceci ne fait que masquer des boutons.
 */
export function offerAccess(post: Pick<Post, "seller" | "is_owner">, contexts: Pick<AvailableContext, "type" | "id" | "capabilities">[]): OfferAccess {
  const seller = post.seller;
  const own = seller ? contexts.find((c) => c.type === seller.context_type && c.id === seller.context_id) : undefined;
  return { canEdit: post.is_owner ?? own?.capabilities.includes("offer.edit") ?? false, isMember: !!own || post.is_owner === true };
}
