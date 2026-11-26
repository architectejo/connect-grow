import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Loader2, Phone } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { AwaitingConfirmationInvitation, Uuid } from "@/api/types";
import { FormAlert } from "@/components/auth/FormFields";
import { RoleBadge } from "@/components/common";
import { ResponsiveDialog } from "@/components/common/ResponsiveDialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useConfirmInvitation } from "@/hooks/use-organization-team";
import { isCompleteCode } from "@/lib/confirmation-code";
import { classifyConfirmInvitationError, isDenyResponse } from "@/lib/invitations";
import { isSensitiveConfirmComplete, scopeLabel, type SensitiveConfirmValue } from "@/lib/team";
import { InviterNoAuthorityWarning } from "./AwaitingInvitationCard";
import { ConfirmationCodeInput } from "./ConfirmationCodeInput";
import { PhoneHint } from "./PhoneHint";
import { LoginUsernameField, SensitiveConfirmFields } from "./SensitiveConfirmFields";
import { useRateBlock } from "./use-rate-block";

interface ConfirmAdminInvitationDialogProps {
  orgId: Uuid;
  orgName: string;
  invitation: AwaitingConfirmationInvitation;
  online: boolean;
  /** Fermeture sans changement (Annuler) : le focus revient au bouton de la carte. */
  onClose: () => void;
  /** La carte disparaît (confirmée, rejetée automatiquement, déjà traitée) : le focus va au titre « À traiter » ou à la liste. */
  onDone: () => void;
  onAnnounce: (message: string) => void;
}

const EMPTY: SensitiveConfirmValue = { confirmed: false, password: "" };

/**
 * E6g : confirmer l'accès d'un administrateur invité avec le code de rattachement (spec D2 §8.3, contrat §7.4.6).
 * Code et mot de passe ne vivent que dans l'état de ce composant : vidés après les échecs prévus par la spec et effacés à la
 * fermeture (démontage + `mutation.reset()`). Le code n'est jamais annoncé, ni mis dans un toast, un titre ou un journal.
 * Aucune relance automatique : un nouvel essai décompterait un essai de code. Seule exception, hors de ce composant :
 * l'intercepteur d'API rejoue une fois la requête après un 401 suivi d'un rafraîchissement du jeton ; le serveur n'a alors
 * compté aucun essai (l'authentification précède tout contrôle du code).
 */
export function ConfirmAdminInvitationDialog({ orgId, orgName, invitation, online, onClose, onDone, onAnnounce }: ConfirmAdminInvitationDialogProps) {
  const { t } = useTranslation();
  const mutation = useConfirmInvitation(orgId);
  const { reset } = mutation;
  const [code, setCode] = useState("");
  const [sensitive, setSensitive] = useState<SensitiveConfirmValue>(EMPTY);
  const [codeError, setCodeError] = useState<string>();
  const [passwordError, setPasswordError] = useState<string>();
  const [formError, setFormError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const codeRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const id = useId();
  const codeId = `${id}-code`;
  const offlineId = `${id}-offline`;
  const pending = mutation.isPending;
  const name = invitation.accepted_by_display_name ?? "";

  // Focus initial sur le champ code (après l'ouverture de Radix, qui place d'abord le focus lui-même)
  useEffect(() => {
    const frame = requestAnimationFrame(() => codeRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, []);
  // Le code et le mot de passe portés par la mutation quittent son état à la fermeture
  useEffect(() => () => reset(), [reset]);

  const clearSecrets = () => {
    setCode("");
    setSensitive(EMPTY);
    reset();
  };

  const canSubmit = online && !pending && !blocked && isCompleteCode(code) && isSensitiveConfirmComplete(sensitive);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (pending || blocked || !online) return;
    setFormError(undefined);
    setCodeError(undefined);
    setPasswordError(undefined);
    if (!isCompleteCode(code)) {
      setCodeError(t("team.confirmInvite.codeIncomplete"));
      codeRef.current?.focus();
      return;
    }
    if (!isSensitiveConfirmComplete(sensitive)) return;
    try {
      await mutation.mutateAsync({ invitationId: invitation.invitation_id, body: { confirm: true, password: sensitive.password, code } });
      clearSecrets();
      const message = t("team.confirmInvite.done", { name });
      toast.success(message);
      onAnnounce(message);
      onDone();
    } catch (error) {
      const failure = classifyConfirmInvitationError(error);
      // Le code et le mot de passe envoyés ne restent pas dans `variables` de la mutation après un échec
      reset();
      // Toute réponse DENY_* : code et mot de passe effacés, quelle que soit l'issue affichée
      if (isDenyResponse(error)) clearSecrets();
      switch (failure.kind) {
        case "gone":
        case "alreadyMember":
          clearSecrets();
          toast.info(failure.message);
          onDone();
          break;
        case "denied":
          clearSecrets();
          toast.error(failure.message);
          onDone();
          break;
        case "exhausted":
          clearSecrets();
          toast.error(failure.message, { duration: 10_000 });
          onAnnounce(failure.message);
          onDone();
          break;
        case "codeRequired":
          setCodeError(failure.message);
          requestAnimationFrame(() => codeRef.current?.focus());
          break;
        case "reauth":
          // Mot de passe faux : aucun essai de code compté, le code est conservé
          setSensitive((value) => ({ ...value, password: "" }));
          setPasswordError(failure.message);
          requestAnimationFrame(() => passwordRef.current?.focus());
          break;
        case "codeInvalid":
          // Code faux : vidé ; le mot de passe (correct) est conservé
          setCode("");
          setCodeError(t("team.confirmInvite.codeInvalid", { name }));
          requestAnimationFrame(() => codeRef.current?.focus());
          break;
        case "unavailable":
          setCode("");
          setSensitive((value) => ({ ...value, password: "" }));
          setFormError(failure.message);
          break;
        case "rate":
          block(failure.retryAfter);
          setFormError(failure.message);
          break;
        default:
          // Réseau coupé (code conservé, aucune relance) ou erreur imprévue : dialogue ouvert
          setFormError(failure.message);
      }
    }
  };

  return (
    <ResponsiveDialog open onOpenChange={(next) => !next && !pending && onClose()} title={t("team.confirmInvite.title", { name })}>
      <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
        {/* Identifiant du compte pour le gestionnaire de mots de passe : le champ code n'est jamais pris pour un identifiant */}
        <LoginUsernameField />
        {invitation.inviter_has_authority === false && <InviterNoAuthorityWarning />}
        <Alert>
          <Phone className="h-4 w-4" aria-hidden />
          <AlertTitle>{t("team.confirmInvite.callTitle")}</AlertTitle>
          <AlertDescription>{t("team.confirmInvite.callBody", { name })}</AlertDescription>
        </Alert>
        <dl className="space-y-2 text-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <dt className="text-muted-foreground">{t("team.confirmInvite.person")}</dt>
            <dd className="font-semibold">{name}</dd>
          </div>
          {invitation.accepted_by_phone_hint && (
            <div className="space-y-1">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <dt className="text-muted-foreground">{t("team.confirmInvite.phone")}</dt>
                <dd className="font-semibold">
                  <PhoneHint hint={invitation.accepted_by_phone_hint} />
                </dd>
              </div>
              <p className="text-xs text-muted-foreground">{t("team.confirmInvite.phoneCheck")}</p>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <dt className="text-muted-foreground">{t("team.confirmInvite.role")}</dt>
            <dd>
              <RoleBadge role={invitation.role} />
            </dd>
          </div>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <dt className="text-muted-foreground">{t("team.confirmInvite.scope")}</dt>
            <dd>{scopeLabel(invitation.scope ?? { type: "ORGANIZATION" }, t)}</dd>
          </div>
        </dl>
        <p className="text-sm">{t("team.confirmInvite.body", { name, org: orgName })}</p>

        <ConfirmationCodeInput
          ref={codeRef}
          id={codeId}
          value={code}
          disabled={pending}
          error={codeError}
          onChange={(digits) => {
            setCode(digits);
            setCodeError(undefined);
          }}
        />

        <SensitiveConfirmFields
          idPrefix={`${id}-sensitive`}
          value={sensitive}
          onChange={(value) => {
            setSensitive(value);
            setPasswordError(undefined);
          }}
          confirmLabel={t("team.confirmInvite.check", { name })}
          error={passwordError}
          disabled={pending}
          passwordRef={passwordRef}
          withUsername={false}
        />

        <FormAlert message={formError} />
        {!online && (
          <p id={offlineId} className="text-xs text-muted-foreground">
            {t("common.offlineAction")}
          </p>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" className="min-h-11" disabled={pending} onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" className="min-h-11" disabled={!canSubmit} aria-describedby={!online ? offlineId : undefined}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("team.confirmInvite.submit")}
          </Button>
        </div>
      </form>
    </ResponsiveDialog>
  );
}
