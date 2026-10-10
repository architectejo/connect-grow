import { Heart, MapPin, Package } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Post } from "@/api/types";
import { useFeatures } from "@/hooks/use-features";
import { formatRelativeDate, formatShortAge } from "@/lib/format";
import { getPostBadges, isSellerVerified, sellerDisplayName } from "@/lib/post";
import { cn } from "@/lib/utils";
import { ImageWithFallback } from "./ImageWithFallback";
import { PriceTag } from "./PriceTag";
import { RatingValue } from "./Rating";
import { StatusBadge } from "./StatusBadge";
import { UserAvatar } from "./UserAvatar";

interface PostCardProps {
  post: Post;
  isFavorite?: boolean;
  /** Affiche le bouton favori quand il est fourni. */
  onToggleFavorite?: (post: Post) => void;
  /** Masque la ligne vendeur (ex. sur la page d'une boutique). */
  hideSeller?: boolean;
  className?: string;
}

/**
 * Carte d'annonce, utilisée partout où une annonce apparaît dans une liste.
 * Toute la carte est cliquable (lien étiré sur le titre) ; le bouton favori reste indépendant.
 */
export function PostCard({ post, isFavorite, onToggleFavorite, hideSeller, className }: PostCardProps) {
  const { t } = useTranslation();
  const { exchangeEnabled } = useFeatures();
  // Une réponse gardée hors ligne peut encore porter le champ : le badge dépend de la configuration, pas seulement de l'annonce
  const exchangeable = exchangeEnabled && !!post.is_exchangeable;
  const badges = getPostBadges(post);
  const sellerName = sellerDisplayName(post.seller);
  const sellerAvatar = post.seller?.business_profile?.logo || post.seller?.photo;

  return (
    <article
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-xl border bg-card text-card-foreground shadow-soft",
        "transition-[transform,box-shadow] duration-300 hover:-translate-y-0.5 hover:shadow-lifted",
        "focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background",
        className,
      )}
    >
      <div className="relative">
        <ImageWithFallback
          src={post.main_image}
          alt={post.title}
          fallbackIcon={Package}
          fallbackLabel={t("post.noImage")}
          wrapperClassName="aspect-[4/3]"
          className="transition-transform duration-500 group-hover:scale-[1.04]"
        />

        {badges.length > 0 && (
          <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5">
            {badges.map((badge) => (
              <StatusBadge key={badge} kind={badge} />
            ))}
          </div>
        )}

        {onToggleFavorite && (
          <button
            type="button"
            onClick={() => onToggleFavorite(post)}
            aria-pressed={!!isFavorite}
            aria-label={isFavorite ? t("post.removeFavorite") : t("post.addFavorite")}
            className="absolute right-2.5 top-2.5 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-background/90 shadow-soft backdrop-blur-sm transition-transform hover:scale-110 active:scale-95"
          >
            <Heart className={cn("h-[18px] w-[18px]", isFavorite ? "fill-destructive text-destructive" : "text-foreground")} />
          </button>
        )}

        {(exchangeable || post.post_type === "SERVICE") && (
          <div className="absolute inset-x-2.5 bottom-2.5 flex flex-wrap gap-1.5">
            {post.post_type === "SERVICE" && <StatusBadge kind="service" className="bg-background/95 backdrop-blur-sm" />}
            {exchangeable && <StatusBadge kind="exchangeable" className="bg-background/95 backdrop-blur-sm" />}
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3 sm:p-4">
        <PriceTag amount={post.price} currency={post.currency} negotiable={post.is_price_negotiable} size="md" />

        <h3 className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-5 text-foreground">
          <Link to={`/post/${post.id}`} className="outline-none after:absolute after:inset-0 after:content-['']">
            {post.title}
          </Link>
        </h3>

        <p className="flex items-center gap-1 text-xs text-muted-foreground">
          <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="truncate">{post.commune_name ?? "Kinshasa"}</span>
          <span aria-hidden>·</span>
          {/* Âge court : sur une carte de 160 px, la commune doit rester lisible */}
          <time dateTime={post.created_at} title={formatRelativeDate(post.created_at)} className="shrink-0">
            {formatShortAge(post.created_at)}
          </time>
        </p>

        {/* Carte d'annonce : la note de l'offre seulement, jamais la note du vendeur ni une note fusionnée */}
        <RatingValue rating={post.offer_rating} kind="offer" />

        {!hideSeller && post.seller && (
          <div className="mt-auto flex items-center gap-2 border-t pt-3">
            <UserAvatar
              src={sellerAvatar}
              name={sellerName}
              size="xs"
              shape={post.seller.user_type === "ENTREPRISE" ? "square" : "circle"}
            />
            <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{sellerName}</span>
            {isSellerVerified(post.seller) && <StatusBadge kind="verified" iconOnly className="text-success" />}
          </div>
        )}
      </div>
    </article>
  );
}
