import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { Uuid } from "@/api/types";
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
import { useRateBlock } from "@/components/team/use-rate-block";
import { useWithdrawAwaitingInvitation } from "@/hooks/use-my-awaiting-invitations";
import { classifyAwaitingActionError } from "@/lib/invitations";

interface WithdrawAwaitingDialogProps {
  invitationId: Uuid;
  organizationName: string;
  online: boolean;
  onClose: () => void;
  /** La demande est retirée (204). */
  onWithdrawn: () => void;
  /** La demande n'était plus en attente (déjà confirmée, rejetée, échue) : listes rechargées par le hook. */
  onGone: () => void;
}

/** Retirer sa demande d'accès (spec D2 §11.4, E15 §9.4 point 7). Focus initial sur « Garder la demande ». */
export function WithdrawAwaitingDialog({ invitationId, organizationName, online, onClose, onWithdrawn, onGone }: WithdrawAwaitingDialogProps) {
  const { t } = useTranslation();
  const mutation = useWithdrawAwaitingInvitation();
  const [formError, setFormError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const pending = mutation.isPending;

  const withdraw = async () => {
    if (pending || blocked || !online) return;
    setFormError(undefined);
    try {
      await mutation.mutateAsync(invitationId);
      onWithdrawn();
    } catch (error) {
      const failure = classifyAwaitingActionError(error, "withdraw");
      if (failure.kind === "gone") {
        toast.info(failure.message);
        onGone();
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
          <AlertDialogTitle>{t("profiles.awaiting.withdrawTitle", { name: organizationName })}</AlertDialogTitle>
          <AlertDialogDescription>{t("profiles.awaiting.withdrawBody")}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormAlert message={formError} />
        {!online && <p className="text-xs text-muted-foreground">{t("common.offlineAction")}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel className="min-h-11" disabled={pending}>
            {t("profiles.awaiting.keep")}
          </AlertDialogCancel>
          <Button type="button" variant="destructive" className="min-h-11" disabled={pending || blocked || !online} onClick={() => void withdraw()}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("profiles.awaiting.withdraw")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
