import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { RatingSummary, Seller } from "@/api/types";
import { formatMonthYear } from "@/lib/format";
import { isSellerVerified, sellerDisplayName } from "@/lib/post";
import { cn } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";
import { RatingBlock } from "./Rating";
import { UserAvatar } from "./UserAvatar";

interface SellerCardProps {
  seller: Seller;
  /** Note du vendeur (contexte vendeur de l'offre), jamais mêlée à la note de l'offre. */
  rating?: RatingSummary;
  /** Lien vers la vitrine du vendeur ; par défaut, sa page publique. */
  href?: string;
  /** Actions (Contacter, S'abonner…) affichées sous l'identité. */
  actions?: ReactNode;
  className?: string;
}

/** Carte vendeur de la fiche annonce : identité, vérification, note du vendeur et ancienneté. */
export function SellerCard({ seller, rating, href, actions, className }: SellerCardProps) {
  const { t } = useTranslation();
  const verified = isSellerVerified(seller);
  const name = sellerDisplayName(seller);
  const isBusiness = seller.user_type === "ENTREPRISE";
  const link = href ?? `/u/${seller.id}`;

  return (
    <section className={cn("rounded-xl border bg-card p-4 shadow-soft sm:p-5", className)}>
      <div className="flex items-start gap-3">
        <Link to={link} className="shrink-0 rounded-xl">
          <UserAvatar
            src={seller.business_profile?.logo || seller.photo}
            name={name}
            size="md"
            shape={isBusiness ? "square" : "circle"}
          />
        </Link>
        <div className="min-w-0 flex-1 space-y-1">
          <Link to={link} className="block truncate font-display font-bold text-foreground hover:text-primary">
            {name}
          </Link>
          {verified && <StatusBadge kind="verified" size="md" />}
        </div>
      </div>

      {rating && (
        <RatingBlock
          kind="seller"
          rating={rating}
          className="mt-3"
          footer={seller.date_joined ? t("rating.memberSince", { date: formatMonthYear(seller.date_joined) }) : undefined}
        />
      )}
      {!rating && seller.date_joined && (
        <p className="mt-3 text-xs text-muted-foreground">{t("rating.memberSince", { date: formatMonthYear(seller.date_joined) })}</p>
      )}

      {actions && <div className="mt-4 grid gap-2">{actions}</div>}
    </section>
  );
}
