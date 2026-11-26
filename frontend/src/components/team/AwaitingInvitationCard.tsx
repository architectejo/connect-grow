import type { Ref } from "react";
import { AlertTriangle, Phone, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AwaitingConfirmationInvitation } from "@/api/types";
import { RoleBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { scopeLabel } from "@/lib/team";
import { PhoneHint } from "./PhoneHint";

/** Avertissement affiché quand l'émetteur n'a plus l'autorité de donner ce rôle (`inviter_has_authority === false`). */
export function InviterNoAuthorityWarning() {
  const { t } = useTranslation();
  return (
    <div className="flex items-start gap-2 rounded-xl border border-warning/50 bg-warning/10 p-3 text-sm text-foreground">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p>{t("team.awaiting.inviterNoAuthority")}</p>
    </div>
  );
}

interface AwaitingInvitationCardProps {
  invitation: AwaitingConfirmationInvitation;
  online: boolean;
  offlineHintId?: string;
  confirmRef?: Ref<HTMLButtonElement>;
  onConfirm: (invitation: AwaitingConfirmationInvitation) => void;
  onReject: (invitation: AwaitingConfirmationInvitation) => void;
}

/**
 * Carte « Demande d'accès à confirmer » (spec D2 §4.5). `can_confirm` : nom abrégé, indice de téléphone, consigne d'appel et
 * boutons ; sinon : carte anonyme sans bouton (le serveur ne renvoie ni nom ni indice). Jamais de code : il n'est pas dans l'objet.
 */
export function AwaitingInvitationCard({ invitation, online, offlineHintId, confirmRef, onConfirm, onReject }: AwaitingInvitationCardProps) {
  const { t } = useTranslation();
  const name = invitation.accepted_by_display_name;
  const canAct = invitation.can_confirm && !!name;
  const createdBy = invitation.is_mine ? t("team.invitations.createdByMe") : t("team.invitations.createdBy", { name: invitation.created_by_display_name });
  const scope = scopeLabel(invitation.scope ?? { type: "ORGANIZATION" }, t);
  const noAuthority = invitation.inviter_has_authority === false;
  const offline = !online ? offlineHintId : undefined;

  return (
    <li className="space-y-2 rounded-2xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <RoleBadge role={invitation.role} />
        <span className="text-sm text-muted-foreground">{scope}</span>
      </div>
      <h4 className="font-semibold">{canAct ? t("team.awaiting.title", { name }) : t("team.awaiting.titleAnonymous")}</h4>
      {canAct && invitation.accepted_by_phone_hint && (
        <p className="text-sm">
          <PhoneHint hint={invitation.accepted_by_phone_hint} />
        </p>
      )}
      {canAct && invitation.accepted_at && (
        <p className="text-sm text-muted-foreground">{t("team.awaiting.acceptedAt", { date: formatDateTime(invitation.accepted_at) })}</p>
      )}
      {invitation.confirmation_expires_at && (
        <p className="text-sm text-muted-foreground">{t("team.awaiting.deadline", { date: formatDateTime(invitation.confirmation_expires_at) })}</p>
      )}
      <p className="text-sm text-muted-foreground">{createdBy}</p>
      {noAuthority && <InviterNoAuthorityWarning />}
      {canAct ? (
        <>
          <p className="flex items-start gap-2 text-sm">
            <Phone className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
            <span>{t("team.awaiting.callHint")}</span>
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              ref={confirmRef}
              type="button"
              className="min-h-11 w-full sm:w-auto"
              disabled={!online}
              aria-describedby={offline}
              aria-label={t("team.awaiting.confirmAria", { name })}
              onClick={() => onConfirm(invitation)}
            >
              {t("team.awaiting.confirm")}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 w-full text-destructive hover:text-destructive sm:w-auto"
              disabled={!online}
              aria-describedby={offline}
              aria-label={t("team.awaiting.rejectAria", { name })}
              onClick={() => onReject(invitation)}
            >
              <X aria-hidden />
              {t("team.awaiting.reject")}
            </Button>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">{t("team.awaiting.notYours")}</p>
      )}
    </li>
  );
}
