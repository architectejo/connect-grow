import { useId, type Ref } from "react";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationMember, OrganizationRole } from "@/api/types";
import { RoleBadge, UserAvatar } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { TableCell, TableRow } from "@/components/ui/table";
import { formatMonthYear } from "@/lib/format";
import { isOwnersOnlyRow, type TeamAction } from "@/lib/team";
import { MemberActionsMenu } from "./MemberActionsMenu";

export interface MemberRowProps {
  member: OrganizationMember;
  actor: { role: OrganizationRole; capabilities: readonly string[] };
  /** `card` : carte empilée (mobile) ; `row` : ligne de tableau (ordinateur). */
  layout: "card" | "row";
  online: boolean;
  offlineHintId?: string;
  triggerRef?: Ref<HTMLButtonElement>;
  onAction: (action: TeamAction, member: OrganizationMember) => void;
}

/**
 * Un membre : nom abrégé, rôle, ancienneté. Aucun téléphone, e-mail ni identifiant de compte (règle 10) :
 * `membership_id` ne sert qu'à désigner la cible d'une action et n'est jamais affiché.
 */
export function MemberRow({ member, actor, layout, online, offlineHintId, triggerRef, onAction }: MemberRowProps) {
  const { t } = useTranslation();
  const helpId = useId();
  const since = formatMonthYear(member.joined_at);
  const lastOwner = member.is_last_effective_owner === true;
  const ownerHint = actor.role === "OWNER" && member.role === "OWNER" && !member.is_self;
  const ownersOnly = isOwnersOnlyRow(actor, member);

  const name = (
    <div className="flex min-w-0 items-center gap-3">
      <UserAvatar name={member.display_name} size="sm" />
      <p className="min-w-0 truncate font-semibold" title={member.display_name}>
        {member.display_name}
        {member.is_self && <span className="ml-1 font-normal text-muted-foreground">{t("team.you")}</span>}
      </p>
    </div>
  );

  const lastOwnerBadge = lastOwner && (
    <>
      <Badge variant="outline" className="gap-1 whitespace-nowrap" title={t("team.lastOwnerHelp")} aria-describedby={helpId}>
        <ShieldAlert className="h-3 w-3" aria-hidden />
        {t("team.lastOwner")}
      </Badge>
      <span id={helpId} className="sr-only">
        {t("team.lastOwnerHelp")}
      </span>
    </>
  );

  const hints = (
    <>
      {ownerHint && <p className="text-xs text-muted-foreground">{t("team.ownerRemoveHint")}</p>}
      {ownersOnly && <p className="text-xs text-muted-foreground">{t("team.ownersOnly")}</p>}
      {lastOwner && member.is_self && <p className="text-xs text-muted-foreground">{t("team.lastOwnerSelfHint")}</p>}
    </>
  );

  const menu = (
    <MemberActionsMenu
      actorRole={actor.role}
      capabilities={actor.capabilities}
      target={member}
      disabled={!online}
      describedBy={offlineHintId}
      triggerRef={triggerRef}
      onAction={onAction}
    />
  );

  if (layout === "row") {
    return (
      <TableRow>
        <TableCell>
          {name}
          {hints}
        </TableCell>
        <TableCell>
          <div className="flex flex-wrap items-center gap-2">
            <RoleBadge role={member.role} />
            {lastOwnerBadge}
          </div>
        </TableCell>
        <TableCell className="whitespace-nowrap text-muted-foreground">{since}</TableCell>
        <TableCell className="w-14 text-right">{menu}</TableCell>
      </TableRow>
    );
  }

  return (
    <li className="space-y-2 rounded-2xl border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        {name}
        {menu}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <RoleBadge role={member.role} />
        {lastOwnerBadge}
      </div>
      {hints}
      <p className="text-xs text-muted-foreground">{t("team.since", { date: since })}</p>
    </li>
  );
}
