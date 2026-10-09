import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Seller } from "@/api/types";
import { formatMonthYear } from "@/lib/format";
import { getSellerTrust, sellerDisplayName } from "@/lib/trust";
import { cn } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";
import { TrustScore } from "./TrustScore";
import { UserAvatar } from "./UserAvatar";

interface SellerCardProps {
  seller: Seller;
  /** Lien vers la vitrine du vendeur ; par défaut, sa page publique. */
  href?: string;
  /** Actions (Contacter, S'abonner…) affichées sous l'identité. */
  actions?: ReactNode;
  className?: string;
}

/** Carte vendeur de la fiche annonce : met en avant la confiance avant le contact. */
export function SellerCard({ seller, href, actions, className }: SellerCardProps) {
  const { t } = useTranslation();
  const trust = getSellerTrust(seller);
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
          <TrustScore trust={trust} size="md" />
          {seller.date_joined && (
            <p className="text-xs text-muted-foreground">
              {t("trust.memberSince", { date: formatMonthYear(seller.date_joined) })}
            </p>
          )}
        </div>
      </div>

      {(trust.isVerified || trust.isReliable) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {trust.isVerified && <StatusBadge kind="verified" size="md" />}
          {trust.isReliable && <StatusBadge kind="reliable" size="md" />}
        </div>
      )}

      {actions && <div className="mt-4 grid gap-2">{actions}</div>}
    </section>
  );
}
