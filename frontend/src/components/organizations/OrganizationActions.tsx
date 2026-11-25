import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Archive, LogOut, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { OrganizationInternal } from "@/api/types";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useArchiveOrganization, useLeaveOrganization } from "@/hooks/use-organizations";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { describeApiError, getApiErrorCode } from "@/lib/api-errors";

/** Carte « Quitter l'organisation » (tous les rôles). `last_owner` reste un message dans la page, pas un blocage de l'interface (D10). */
export function LeaveOrganizationCard({ org, titleKey = "org.home.leaveTitle", bodyKey = "org.home.leaveBody" }: { org: Pick<OrganizationInternal, "id">; titleKey?: string; bodyKey?: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const { leaveActive } = useActiveContext();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string>();
  const leave = useLeaveOrganization(org.id, () => leaveActive({ type: "ORGANIZATION", id: org.id }, "left"));
  const titleId = useId();

  const confirm = async () => {
    setError(undefined);
    try {
      await leave.mutateAsync();
      toast.success(t("team.left"));
      navigate("/profiles", { replace: true });
    } catch (err) {
      setOpen(false);
      const code = getApiErrorCode(err);
      if (code === "DENY_RELATION") {
        // Déjà retiré de l'organisation : même issue qu'un départ réussi
        toast.info(t("org.home.alreadyLeft"));
        navigate("/profiles", { replace: true });
        return;
      }
      setError(describeApiError(err, { inOrganization: true }));
    }
  };

  return (
    <section aria-labelledby={titleId} className="rounded-2xl border bg-card p-5 shadow-soft">
      <h2 id={titleId} className="font-display text-lg font-bold">
        {t(titleKey)}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{t(bodyKey)}</p>
      {error && (
        <Alert variant="destructive" role="alert" className="mt-3">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Button
        type="button"
        variant="outline"
        className="mt-4 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
        disabled={!online || leave.isPending}
        aria-describedby={!online ? `${titleId}-offline` : undefined}
        onClick={() => setOpen(true)}
      >
        <LogOut aria-hidden /> {t("team.leaveConfirm")}
      </Button>
      {!online && (
        <p id={`${titleId}-offline`} className="mt-2 text-xs text-muted-foreground">
          {t("common.offlineAction")}
        </p>
      )}

      <AlertDialog open={open} onOpenChange={(next) => !leave.isPending && setOpen(next)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("team.leaveTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("team.leaveBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={leave.isPending}>{t("common.cancel")}</AlertDialogCancel>
            <Button type="button" variant="destructive" onClick={() => void confirm()} disabled={leave.isPending}>
              {leave.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t("team.leaveConfirm")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}

/** Carte « Archiver l'organisation » (propriétaire seulement : capacité `org.archive`). Consentement explicite requis. */
export function ArchiveOrganizationCard({ org }: { org: OrganizationInternal }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const { active, switchToPersonal } = useActiveContext();
  const [open, setOpen] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const [error, setError] = useState<string>();
  // Archivage voulu par le propriétaire : retour silencieux au profil personnel, la vue « Archivée » explique l'état (pas d'alerte de perte)
  const archive = useArchiveOrganization(org.id, () => {
    if (active.type === "ORGANIZATION" && active.id === org.id) switchToPersonal();
  });
  const titleId = useId();
  const consentId = useId();

  if (!org.capabilities.includes("org.archive")) return null;

  const confirm = async () => {
    setError(undefined);
    try {
      await archive.mutateAsync();
      toast.success(t("org.unavailable.archivedDone"));
      navigate(`/organizations/${org.id}`, { replace: true });
    } catch (err) {
      setOpen(false);
      setError(describeApiError(err, { inOrganization: true }));
    }
  };

  return (
    <section aria-labelledby={titleId} className="rounded-2xl border bg-card p-5 shadow-soft">
      <h2 id={titleId} className="font-display text-lg font-bold">
        {t("org.home.archiveTitle")}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{t("org.home.archiveBody")}</p>
      {error && (
        <Alert variant="destructive" role="alert" className="mt-3">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Button
        type="button"
        variant="outline"
        className="mt-4 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
        disabled={!online || archive.isPending}
        onClick={() => {
          setUnderstood(false);
          setOpen(true);
        }}
      >
        <Archive aria-hidden /> {t("team.archiveConfirm")}
      </Button>
      {!online && <p className="mt-2 text-xs text-muted-foreground">{t("common.offlineAction")}</p>}

      <AlertDialog open={open} onOpenChange={(next) => !archive.isPending && setOpen(next)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("team.archiveTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("team.archiveBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex items-center gap-2">
            <Checkbox id={consentId} checked={understood} onCheckedChange={(checked) => setUnderstood(checked === true)} />
            <Label htmlFor={consentId} className="cursor-pointer text-sm">
              {t("team.archiveConsent")}
            </Label>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={archive.isPending}>{t("common.cancel")}</AlertDialogCancel>
            <Button type="button" variant="destructive" onClick={() => void confirm()} disabled={!understood || archive.isPending}>
              {archive.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t("team.archiveConfirm")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
