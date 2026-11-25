import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
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

interface DeclineInvitationDialogProps {
  pending: boolean;
  onKeep: () => void;
  onDecline: () => void;
}

/** Refuser une invitation (page d'acceptation). Focus initial sur « Garder l'invitation » (l'action sûre). */
export function DeclineInvitationDialog({ pending, onKeep, onDecline }: DeclineInvitationDialogProps) {
  const { t } = useTranslation();
  return (
    <AlertDialog open onOpenChange={(next) => !next && !pending && onKeep()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("invitation.declineTitle")}</AlertDialogTitle>
          <AlertDialogDescription>{t("invitation.declineBody")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{t("invitation.keep")}</AlertDialogCancel>
          <Button type="button" variant="destructive" disabled={pending} onClick={onDecline}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("invitation.declineConfirm")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
