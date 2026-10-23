import { useTranslation } from "react-i18next";
import { Building2, Briefcase, UserRound } from "lucide-react";
import { useActiveContext } from "@/contexts/ActiveContextContext";

const ICONS = { USER: UserRound, PROVIDER: Briefcase, ORGANIZATION: Building2 } as const;

/** « Offres et statistiques de : {nom du profil actif} » : dit à qui appartiennent les données de la page. */
export function ScopeLine({ className }: { className?: string }) {
  const { t } = useTranslation();
  const { active } = useActiveContext();
  const Icon = ICONS[active.type];
  return (
    <p className={className ?? "mt-1 flex items-center gap-1.5 text-sm text-muted-foreground"}>
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      <span className="min-w-0 truncate" title={active.name}>
        {t("scope.offersOf", { name: active.name })}
      </span>
    </p>
  );
}
