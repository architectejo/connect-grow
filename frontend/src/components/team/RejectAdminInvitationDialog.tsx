import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { AwaitingConfirmationInvitation, Uuid } from "@/api/types";
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
import { useRejectInvitation } from "@/hooks/use-organization-team";
import { classifyRejectInvitationError } from "@/lib/invitations";
import { useRateBlock } from "./use-rate-block";

interface RejectAdminInvitationDialogProps {
  orgId: Uuid;
  invitation: AwaitingConfirmationInvitation;
  online: boolean;
  onClose: () => void;
  /** La carte disparaît (rejetée, ou déjà traitée). */
  onDone: () => void;
  onAnnounce: (message: string) => void;
}

/** E6h : rejeter une demande d'accès (spec D2 §8.4). Focus initial sur « Garder la demande » ; ni mot de passe ni code. */
export function RejectAdminInvitationDialog({ orgId, invitation, online, onClose, onDone, onAnnounce }: RejectAdminInvitationDialogProps) {
  const { t } = useTranslation();
  const mutation = useRejectInvitation(orgId);
  const [formError, setFormError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const pending = mutation.isPending;
  const name = invitation.accepted_by_display_name;

  const reject = async () => {
    if (pending || blocked || !online) return;
    setFormError(undefined);
    try {
      await mutation.mutateAsync(invitation.invitation_id);
      const message = t("team.rejectInvite.done");
      toast.success(message);
      onAnnounce(message);
      onDone();
    } catch (error) {
      const failure = classifyRejectInvitationError(error);
      if (failure.kind === "gone") {
        toast.info(failure.message);
        onDone();
      } else if (failure.kind === "denied") {
        toast.error(failure.message);
        onDone();
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
          <AlertDialogTitle>{name ? t("team.rejectInvite.title", { name }) : t("team.rejectInvite.titleAnonymous")}</AlertDialogTitle>
          <AlertDialogDescription>{t("team.rejectInvite.body")}</AlertDialogDescription>
        </AlertDialogHeader>
        {invitation.inviter_has_authority === false && <p className="text-sm">{t("team.rejectInvite.inviterNoAuthority")}</p>}
        <p className="text-sm">{t("team.rejectInvite.when")}</p>
        <FormAlert message={formError} />
        {!online && <p className="text-xs text-muted-foreground">{t("common.offlineAction")}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel className="min-h-11" disabled={pending}>
            {t("team.rejectInvite.keep")}
          </AlertDialogCancel>
          <Button type="button" variant="destructive" className="min-h-11" disabled={pending || blocked || !online} onClick={() => void reject()}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("team.rejectInvite.submit")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
