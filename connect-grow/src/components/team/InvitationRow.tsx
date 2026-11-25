import type { Ref } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationInvitation } from "@/api/types";
import { RoleBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { formatLongDate } from "@/lib/format";
import { isInvitationExpired } from "@/lib/invitations";

export interface InvitationRowProps {
  invitation: OrganizationInvitation;
  /** `card` : carte empilée (mobile) ; `row` : ligne de tableau (ordinateur). */
  layout: "card" | "row";
  /** L'appelant peut annuler (capacité `org.manage_members`). */
  canRevoke: boolean;
  online: boolean;
  offlineHintId?: string;
  triggerRef?: Ref<HTMLButtonElement>;
  onRevoke: (invitation: OrganizationInvitation) => void;
}

/**
 * Une invitation en attente : rôle, étiquette, créateur, échéance. Jamais le jeton ni son empreinte (le serveur ne les renvoie pas).
 * Une ligne expirée porte « Expirée » et aucun bouton d'annulation (le serveur répondrait `invitation_not_pending`).
 */
export function InvitationRow({ invitation, layout, canRevoke, online, offlineHintId, triggerRef, onRevoke }: InvitationRowProps) {
  const { t } = useTranslation();
  const expired = isInvitationExpired(invitation);
  const label = invitation.label.trim();
  const labelText = label || t("team.invitations.noLabel");
  const createdBy = invitation.is_mine ? t("team.invitations.createdByMe") : t("team.invitations.createdBy", { name: invitation.created_by_display_name });
  const date = formatLongDate(invitation.expires_at);

  const labelNode = (
    <span className={label ? "block min-w-0 truncate font-semibold" : "block min-w-0 truncate text-muted-foreground"} title={label || undefined}>
      {labelText}
    </span>
  );
  const expiredBadge = expired && <Badge variant="outline">{t("team.invitations.expired")}</Badge>;
  const action =
    canRevoke && !expired ? (
      <Button
        ref={triggerRef}
        type="button"
        variant="outline"
        size="sm"
        className="min-h-11"
        disabled={!online}
        aria-describedby={!online ? offlineHintId : undefined}
        aria-label={t("team.invitations.revokeLabel", { label: labelText, role: t(`role.${invitation.role}`), date })}
        onClick={() => onRevoke(invitation)}
      >
        <X aria-hidden />
        {t("team.invitations.revoke")}
      </Button>
    ) : null;

  if (layout === "row") {
    return (
      <TableRow>
        <TableCell>
          <RoleBadge role={invitation.role} />
        </TableCell>
        <TableCell className="max-w-[16rem]">{labelNode}</TableCell>
        <TableCell className="text-muted-foreground">{createdBy}</TableCell>
        <TableCell className="whitespace-nowrap text-muted-foreground">
          {expired ? expiredBadge : date}
        </TableCell>
        <TableCell className="text-right">{action}</TableCell>
      </TableRow>
    );
  }

  return (
    <li className="space-y-2 rounded-2xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <RoleBadge role={invitation.role} />
        {expiredBadge}
      </div>
      {labelNode}
      <p className="text-sm text-muted-foreground">{createdBy}</p>
      {!expired && <p className="text-xs text-muted-foreground">{t("team.invitations.expires", { date })}</p>}
      {action}
    </li>
  );
}
