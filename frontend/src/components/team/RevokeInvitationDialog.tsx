import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { OrganizationInvitation, Uuid } from "@/api/types";
import { FormAlert } from "@/components/auth/FormFields";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useRevokeInvitation } from "@/hooks/use-organization-team";
import { getApiErrorCode } from "@/lib/api-errors";
import { classifyTeamError } from "@/lib/team";
import { useRateBlock } from "./use-rate-block";

interface RevokeInvitationDialogProps {
  orgId: Uuid;
  invitation: OrganizationInvitation;
  online: boolean;
  /** Fermeture sans annulation de l'invitation. */
  onClose: () => void;
  /** L'invitation n'est plus en attente (annulée par cette action, ou déjà close) : le focus passe au titre de la liste. */
  onRevoked: () => void;
  onAnnounce: (message: string) => void;
}

/** E6e : annuler une invitation. Focus initial sur « Garder l'invitation » (l'action sûre) ; « Annuler » seul serait ambigu. */
export function RevokeInvitationDialog({ orgId, invitation, online, onClose, onRevoked, onAnnounce }: RevokeInvitationDialogProps) {
  const { t } = useTranslation();
  const mutation = useRevokeInvitation(orgId);
  const [formError, setFormError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const pending = mutation.isPending;

  const confirm = async () => {
    if (pending || blocked || !online) return;
    setFormError(undefined);
    try {
      await mutation.mutateAsync(invitation.invitation_id);
      const message = t("team.invitations.revoked");
      toast.success(message);
      onAnnounce(message);
      onRevoked();
    } catch (error) {
      const code = getApiErrorCode(error);
      if (code === "invitation_not_pending" || code === "invitation_not_found") {
        toast.info(t("team.invitations.notPending"));
        onRevoked();
        return;
      }
      const failure = classifyTeamError(error);
      if (failure.kind === "denied") {
        toast.error(failure.message);
        onClose();
      } else {
        if (failure.kind === "rate") block(failure.retryAfter);
        setFormError(failure.message);
      }
    }
  };

  return (
    <AlertDialog open onOpenChange={(next) => !next && !pending && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("team.invitations.revokeTitle")}</AlertDialogTitle>
          <AlertDialogDescription>{t("team.invitations.revokeBody")}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormAlert message={formError} />
        {!online && <p className="text-xs text-muted-foreground">{t("common.offlineAction")}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel className="min-h-11" disabled={pending}>{t("team.invitations.keep")}</AlertDialogCancel>
          <Button type="button" variant="destructive" className="min-h-11" disabled={pending || blocked || !online} onClick={() => void confirm()}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("team.invitations.revoke")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
