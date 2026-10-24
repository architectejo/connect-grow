import { ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationRole } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** Rôle dans une organisation : texte et icône, jamais la couleur seule. */
export function RoleBadge({ role, className }: { role: OrganizationRole; className?: string }) {
  const { t } = useTranslation();
  return (
    <Badge variant="secondary" className={cn("gap-1 whitespace-nowrap", className)}>
      <ShieldCheck className="h-3 w-3" aria-hidden />
      {t(`role.${role}`)}
    </Badge>
  );
}
