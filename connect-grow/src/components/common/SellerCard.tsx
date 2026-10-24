import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { RatingSummary, Seller } from "@/api/types";
import { formatMonthYear } from "@/lib/format";
import { sellerDisplayName, sellerPathOf } from "@/lib/post";
import { cn } from "@/lib/utils";
import { RatingBlock } from "./Rating";
import { SellerTypeBadge } from "./SellerTypeBadge";
import { UserAvatar } from "./UserAvatar";
import { VerifiedClaims } from "./VerifiedClaims";

interface SellerCardProps {
  seller: Seller;
  /** Note du vendeur (contexte vendeur de l'offre), jamais mêlée à la note de l'offre. */
  rating?: RatingSummary;
  /** Lien vers la page publique du vendeur ; par défaut, `/seller/<type>/<id>`. */
  href?: string;
  /** Actions (Contacter, S'abonner…) affichées sous l'identité. */
  actions?: ReactNode;
  className?: string;
}

/**
 * Carte vendeur de la fiche annonce : identité, type de vendeur, mentions de vérification précises, note de CE
 * vendeur et ancienneté. Aucun « vérifié » seul, aucun score de confiance (règles 3 et 4).
 */
export function SellerCard({ seller, rating, href, actions, className }: SellerCardProps) {
  const { t } = useTranslation();
  const name = sellerDisplayName(seller);
  const link = href ?? sellerPathOf(seller);
  const since = seller.member_since ? t("rating.memberSince", { date: formatMonthYear(seller.member_since) }) : undefined;

  return (
    <section className={cn("rounded-xl border bg-card p-4 shadow-soft sm:p-5", className)}>
      <div className="flex items-start gap-3">
        <Link to={link} className="shrink-0 rounded-xl" aria-label={name}>
          <UserAvatar src={seller.photo} name={name} size="md" shape={seller.context_type === "ORGANIZATION" ? "square" : "circle"} />
        </Link>
        <div className="min-w-0 flex-1 space-y-1.5">
          <Link to={link} className="block truncate font-display font-bold text-foreground hover:text-primary" title={name}>
            {name}
          </Link>
          <SellerTypeBadge contextType={seller.context_type} orgType={seller.org_type} />
          <VerifiedClaims claims={seller.verified_claims} summary={seller.verification_summary} />
        </div>
      </div>

      {rating && <RatingBlock kind="seller" rating={rating} className="mt-3" footer={since} />}
      {!rating && since && <p className="mt-3 text-xs text-muted-foreground">{since}</p>}

      {actions && <div className="mt-4 grid gap-2">{actions}</div>}
    </section>
  );
}
