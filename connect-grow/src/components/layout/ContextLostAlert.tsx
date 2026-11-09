import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { UserRoundX } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import type { LostReason } from "@/lib/active-context";
import { lostMessageKey } from "@/lib/api-errors";

interface ContextLostAlertProps {
  reason: LostReason;
  lostName: string;
  /** Organisation perdue : le lien « Voir l'état » n'apparaît que si le serveur la confirme suspendue ou archivée. */
  lostId?: string;
  onDismiss: () => void;
}

/**
 * Retour forcé au profil personnel : alerte persistante (jamais un simple toast, jamais un repli silencieux).
 * Elle reste jusqu'à fermeture, y compris après navigation. Le focus lui est donné à l'apparition.
 */
export function ContextLostAlert({ reason, lostName, lostId, onDismiss }: ContextLostAlertProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const showStatusLink = !!lostId && (reason === "org_suspended" || reason === "org_archived");

  useEffect(() => {
    ref.current?.focus();
  }, [reason, lostName]);

  return (
    <Alert ref={ref} variant="destructive" tabIndex={-1} className="mb-4 bg-background outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <UserRoundX className="h-4 w-4" aria-hidden />
      <AlertTitle>{t("errors.lost.title")}</AlertTitle>
      <AlertDescription className="space-y-1">
        <p>{t(lostMessageKey(reason))}</p>
        {lostName && <p className="text-xs">{t("errors.lost.profile", { name: lostName })}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {showStatusLink && (
            <Button asChild variant="outline" size="sm">
              <Link to={`/organizations/${lostId}`} onClick={onDismiss}>
                {t("org.unavailable.seeFromAlert")}
              </Link>
            </Button>
          )}
          <Button type="button" variant="outline" size="sm" onClick={onDismiss}>
            {t("errors.lost.dismiss")}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}

/** Emplacement de l'alerte, monté dans le gabarit des pages. */
export function ContextLostAlertHost() {
  const { lost, dismissLost } = useActiveContext();
  if (!lost) return null;
  return <ContextLostAlert reason={lost.reason} lostName={lost.lostName} lostId={lost.lostId} onDismiss={dismissLost} />;
}
