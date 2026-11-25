import { useTranslation } from "react-i18next";
import { Archive, PauseCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface OrganizationStatusBadgeProps {
  status: "SUSPENDED" | "ARCHIVED";
  className?: string;
}

/**
 * Statut d'une organisation indisponible. Le texte est toujours présent (jamais la couleur seule) ;
 * volontairement distinct de `StatusBadge`, réservé à « Sponsorisé » et aux mentions de promotion (règle 5).
 */
export function OrganizationStatusBadge({ status, className }: OrganizationStatusBadgeProps) {
  const { t } = useTranslation();
  const label = t(`org.status.${status}`);
  const Icon = status === "SUSPENDED" ? PauseCircle : Archive;
  return (
    <Badge variant="outline" role="img" aria-label={t("org.status.aria", { status: label })} className={cn("gap-1 whitespace-nowrap", className)}>
      <Icon className="h-3 w-3" aria-hidden />
      {label}
    </Badge>
  );
}
