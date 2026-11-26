import { useEffect, useId, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { MyAwaitingInvitation } from "@/api/types";
import { FormAlert } from "@/components/auth/FormFields";
import { ResponsiveDialog } from "@/components/common/ResponsiveDialog";
import { ConfirmationCodeDisplay } from "@/components/team/ConfirmationCodeDisplay";
import { useRateBlock } from "@/components/team/use-rate-block";
import { Button } from "@/components/ui/button";
import { useRegenerateConfirmationCode } from "@/hooks/use-my-awaiting-invitations";
import { formatDateTime } from "@/lib/format";
import { classifyAwaitingActionError } from "@/lib/invitations";

interface NewConfirmationCodeDialogProps {
  invitation: MyAwaitingInvitation;
  online: boolean;
  /** Fermeture (avec ou sans nouveau code) : le focus revient au bouton « Obtenir un nouveau code » de la carte. */
  onClose: () => void;
  /** La demande n'est plus en attente : listes rechargées par le hook. */
  onGone: () => void;
  onAnnounce: (message: string) => void;
}

/** Code affiché à l'étape 2 : état local seulement (la mutation est remise à zéro dès réception). */
interface ShownCode {
  code: string;
  expiresAt: string;
}

/**
 * E17 « Obtenir un nouveau code » (spec D2 §11.3), en deux étapes : avertissement (l'ancien code ne fonctionnera plus), puis code
 * affiché, non fermable par clic extérieur. Aucune relance automatique : un second appel invaliderait le code affiché (seule
 * exception : l'intercepteur d'API rejoue une fois après un 401 suivi d'un rafraîchissement du jeton, requête alors non traitée).
 */
export function NewConfirmationCodeDialog({ invitation, online, onClose, onGone, onAnnounce }: NewConfirmationCodeDialogProps) {
  const { t } = useTranslation();
  const mutation = useRegenerateConfirmationCode();
  const { reset } = mutation;
  const [shown, setShown] = useState<ShownCode | null>(null);
  const [formError, setFormError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const codeHeadingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const offlineId = useId();
  const pending = mutation.isPending;

  useEffect(() => () => reset(), [reset]);
  useEffect(() => {
    if (!shown) return;
    const frame = requestAnimationFrame(() => codeHeadingRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [shown]);

  const close = () => {
    setShown(null);
    reset();
    onClose();
  };

  const request = async () => {
    if (pending || blocked || !online) return;
    setFormError(undefined);
    try {
      const data = await mutation.mutateAsync(invitation.invitation_id);
      setShown({ code: data.confirmation_code, expiresAt: data.confirmation_expires_at });
      reset();
      onAnnounce(t("profiles.awaiting.newCodeAnnounce"));
    } catch (error) {
      const failure = classifyAwaitingActionError(error, "newCode");
      if (failure.kind === "gone") {
        toast.info(failure.message);
        onGone();
        return;
      }
      if (failure.kind === "rate") block(failure.retryAfter);
      setFormError(failure.message);
    }
  };

  if (shown) {
    return (
      <ResponsiveDialog open dismissible={false} onOpenChange={(next) => !next && close()} title={t("profiles.awaiting.newCodeShown")}>
        <div className="space-y-4">
          <ConfirmationCodeDisplay ref={codeHeadingRef} code={shown.code} headingId={headingId} />
          <p className="text-center text-sm font-semibold">{t("invitation.awaiting.deadline", { date: formatDateTime(shown.expiresAt) })}</p>
          <Button type="button" className="min-h-11 w-full" onClick={close}>
            {t("profiles.awaiting.newCodeDone")}
          </Button>
        </div>
      </ResponsiveDialog>
    );
  }

  return (
    <ResponsiveDialog open onOpenChange={(next) => !next && !pending && close()} title={t("profiles.awaiting.newCodeTitle")}>
      <div className="space-y-4">
        <p className="text-sm">{t("profiles.awaiting.newCodeBody", { name: invitation.organization_name })}</p>
        <FormAlert message={formError} />
        {!online && (
          <p id={offlineId} className="text-xs text-muted-foreground">
            {t("common.offlineAction")}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" className="min-h-11" autoFocus disabled={pending} onClick={close}>
            {t("profiles.awaiting.newCodeKeep")}
          </Button>
          <Button type="button" className="min-h-11" disabled={pending || blocked || !online} aria-describedby={!online ? offlineId : undefined} onClick={() => void request()}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("profiles.awaiting.newCodeSubmit")}
          </Button>
        </div>
      </div>
    </ResponsiveDialog>
  );
}
