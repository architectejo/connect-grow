import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import type { AvailableContext } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { dismissLegacyNotice, isLegacyNoticeDismissed, migratedOrganizations } from "@/lib/legacy-notice";

function Notice({ organization, onDismiss }: { organization: Pick<AvailableContext, "type" | "id" | "name">; onDismiss: () => void }) {
  const { t } = useTranslation();
  const { setActive, active } = useActiveContext();
  const isActive = active.type === "ORGANIZATION" && active.id === organization.id;
  return (
    <Alert className="mb-4">
      <Info className="h-4 w-4" aria-hidden />
      <AlertTitle>{t("legacy.title")}</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>{t("legacy.body", { name: organization.name })}</p>
        <p>{t("legacy.contact")}</p>
        <div className="flex flex-wrap gap-2 pt-1">
          {!isActive && (
            <Button type="button" size="sm" onClick={() => setActive(organization)}>
              {t("legacy.action")}
            </Button>
          )}
          <Button type="button" size="sm" variant="outline" onClick={onDismiss}>
            {t("legacy.dismiss")}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}

/**
 * Message d'information pour chaque organisation migrée (E14). Fermable, fermeture mémorisée par organisation.
 * `only` limite l'affichage à une organisation (page de cette organisation).
 */
export function LegacyOrgNotice({ only }: { only?: string }) {
  const { contexts } = useActiveContext();
  const [, bump] = useState(0);
  const list = migratedOrganizations(contexts).filter((c) => (only ? c.id === only : true) && !isLegacyNoticeDismissed(c.id));
  if (list.length === 0) return null;
  return (
    <>
      {list.map((organization) => (
        <Notice
          key={organization.id}
          organization={organization}
          onDismiss={() => {
            dismissLegacyNotice(organization.id);
            bump((n) => n + 1);
          }}
        />
      ))}
    </>
  );
}
