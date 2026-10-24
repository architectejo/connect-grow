import { useTranslation } from "react-i18next";
import { UserRound } from "lucide-react";
import { useOptionalActiveContext } from "@/contexts/ActiveContextContext";
import { cn } from "@/lib/utils";

/**
 * Rappel sur les actions toujours faites avec le profil personnel (contact, avis, favoris, signalement) :
 * le serveur ignore l'en-tête X-Context pour elles (ADR 0006 §6.4). Affiché seulement hors profil personnel.
 */
export function AlwaysPersonalNote({ className }: { className?: string }) {
  const { t } = useTranslation();
  const active = useOptionalActiveContext()?.active;
  if (!active || active.type === "USER") return null;
  return (
    <p className={cn("flex items-center gap-1.5 text-xs text-muted-foreground", className)}>
      <UserRound className="h-3.5 w-3.5 shrink-0" aria-hidden /> {t("context.alwaysPersonal")}
    </p>
  );
}
