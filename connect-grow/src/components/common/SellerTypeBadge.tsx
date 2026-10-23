import { Briefcase, Building2, UserRound, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationType, SellerContextType } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const ICONS: Record<SellerContextType, LucideIcon> = { USER: UserRound, PROVIDER: Briefcase, ORGANIZATION: Building2 };

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Libellé du type de vendeur : « Particulier », « Prestataire », « Organisation · Boutique » (forme complète) ou « Boutique » (compacte). */
export function sellerTypeLabel(t: Translate, contextType: SellerContextType, orgType?: OrganizationType | null, compact = false): string {
  const group = compact ? "seller.typeCompact" : "seller.type";
  if (contextType === "ORGANIZATION") {
    return t(`${group}.ORGANIZATION`, { orgType: orgType ? t(`orgType.${orgType}`) : t("context.type.ORGANIZATION") });
  }
  return t(`${group}.${contextType}`);
}

interface SellerTypeBadgeProps {
  contextType: SellerContextType;
  orgType?: OrganizationType | null;
  compact?: boolean;
  className?: string;
}

/**
 * Type de vendeur, toujours visible (CDC 3.3). Neutre, jamais vert : le vert est réservé aux mentions de vérification.
 * Le libellé est toujours écrit (pas d'icône seule).
 */
export function SellerTypeBadge({ contextType, orgType, compact = false, className }: SellerTypeBadgeProps) {
  const { t } = useTranslation();
  const Icon = ICONS[contextType];
  return (
    <Badge variant="outline" className={cn("gap-1 whitespace-nowrap bg-background font-medium", className)}>
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      <span className="truncate">{sellerTypeLabel(t as Translate, contextType, orgType, compact)}</span>
    </Badge>
  );
}
