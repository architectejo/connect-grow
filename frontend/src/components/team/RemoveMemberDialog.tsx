import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { OrganizationMember, Uuid } from "@/api/types";
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
import { useRemoveMember } from "@/hooks/use-organization-team";
import { classifyTeamError } from "@/lib/team";
import { useRateBlock } from "./use-rate-block";

interface RemoveMemberDialogProps {
  orgId: Uuid;
  member: OrganizationMember;
  online: boolean;
  /** Fermeture sans retrait (annulation ou refus). */
  onClose: () => void;
  /** Le membre n'est plus dans l'équipe (retiré par cette action, ou déjà retiré) : le focus passe au titre de la liste. */
  onRemoved: () => void;
  onAnnounce: (message: string) => void;
}

/** E6d : retirer un membre. Pas de mot de passe (le contrat n'en exige pas). Focus initial sur « Annuler ». */
export function RemoveMemberDialog({ orgId, member, online, onClose, onRemoved, onAnnounce }: RemoveMemberDialogProps) {
  const { t } = useTranslation();
  const mutation = useRemoveMember(orgId);
  const [formError, setFormError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const pending = mutation.isPending;

  const confirm = async () => {
    if (pending || blocked || !online) return;
    setFormError(undefined);
    try {
      await mutation.mutateAsync(member.membership_id);
      const message = t("team.removed", { name: member.display_name });
      toast.success(message);
      onAnnounce(message);
      onRemoved();
    } catch (error) {
      const failure = classifyTeamError(error);
      if (failure.kind === "gone") {
        // Déjà retiré : même issue qu'un succès
        toast.info(failure.message);
        onRemoved();
      } else if (failure.kind === "denied") {
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
          <AlertDialogTitle>{t("team.removeTitle", { name: member.display_name })}</AlertDialogTitle>
          <AlertDialogDescription>{t("team.removeBody", { name: member.display_name })}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormAlert message={formError} />
        {!online && <p className="text-xs text-muted-foreground">{t("common.offlineAction")}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{t("common.cancel")}</AlertDialogCancel>
          <Button type="button" variant="destructive" disabled={pending || blocked || !online} onClick={() => void confirm()}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("team.removeButton")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
