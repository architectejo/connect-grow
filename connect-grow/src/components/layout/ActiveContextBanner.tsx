import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { ContextSwitcher } from "./ContextSwitcher";

/**
 * Bandeau « vous agissez en tant que… » du header (CDC 3.1 : le profil actif est toujours affiché).
 * Mobile : toujours présent, bouton qui ouvre la feuille de choix. Desktop : seulement hors profil personnel
 * (la pastille de la barre suffit au profil personnel).
 */
export function ActiveContextBanner() {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();
  const { active, switchToPersonal } = useActiveContext();
  if (!isAuthenticated) return null;

  const text =
    active.type === "ORGANIZATION"
      ? t("context.bannerOrganization", { name: active.name, role: active.role ? t(`role.${active.role}`) : "" }).replace(/ · $/, "")
      : active.type === "PROVIDER"
        ? t("context.bannerProvider", { name: active.name })
        : t("context.bannerPersonal");

  return (
    <>
      <div role="region" aria-label={t("context.active")} className="md:hidden">
        <ContextSwitcher variant="banner" showManagementLinks={MANAGEMENT_LINKS_READY} />
      </div>
      {active.type !== "USER" && (
        <div
          role="region"
          aria-label={t("context.active")}
          className="hidden h-9 items-center justify-between gap-4 border-b border-primary/30 bg-primary/10 px-4 text-sm text-foreground md:flex"
        >
          <p className="truncate font-medium" title={text}>
            {text}
          </p>
          <Button type="button" variant="link" size="sm" className="h-auto shrink-0 p-0" onClick={switchToPersonal}>
            {t("context.switchToPersonal")}
          </Button>
        </div>
      )}
    </>
  );
}

/** Passe à true quand les écrans « Mes profils » et « Créer une organisation » existent (F2). */
export const MANAGEMENT_LINKS_READY = false;
