import type { Ref } from "react";
import { ArrowRightLeft, MoreHorizontal, UserCog, UserMinus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationMember, OrganizationRole } from "@/api/types";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { memberActions, type TeamAction } from "@/lib/team";

interface MemberActionsMenuProps {
  actorRole: OrganizationRole;
  capabilities: readonly string[];
  target: OrganizationMember;
  /** Hors ligne : le déclencheur est désactivé (aucune action n'est mise en file). */
  disabled?: boolean;
  /** Reliée au texte « Reconnectez-vous… » quand `disabled` vient d'une coupure réseau. */
  describedBy?: string;
  triggerRef?: Ref<HTMLButtonElement>;
  onAction: (action: TeamAction, member: OrganizationMember) => void;
}

/**
 * Menu `⋯` d'une ligne. Les entrées suivent la matrice rôle de l'acteur / rôle de la cible (`memberActions`) :
 * aucun menu sur sa propre ligne, « Retirer » absent sur un administrateur principal. Les fenêtres sont montées par la page, hors du menu,
 * pour que le focus revienne au bouton à la fermeture.
 */
export function MemberActionsMenu({ actorRole, capabilities, target, disabled, describedBy, triggerRef, onAction }: MemberActionsMenuProps) {
  const { t } = useTranslation();
  const actions = memberActions({ role: actorRole, capabilities }, target);
  if (actions.length === 0) return null;
  const hasRemove = actions.includes("remove");
  const regular = actions.filter((action) => action !== "remove");
  const icons = { changeRole: UserCog, transfer: ArrowRightLeft, remove: UserMinus } as const;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          ref={triggerRef}
          type="button"
          variant="ghost"
          size="icon"
          className="min-h-11 min-w-11"
          disabled={disabled}
          aria-label={t("team.menuLabel", { name: target.display_name })}
          aria-describedby={disabled ? describedBy : undefined}
        >
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {regular.map((action) => {
          const Icon = icons[action];
          return (
            <DropdownMenuItem key={action} className="min-h-11 gap-2" onSelect={() => onAction(action, target)}>
              <Icon className="h-4 w-4" aria-hidden />
              {action === "transfer" ? t("team.transferTo", { name: target.display_name }) : t(`team.${action}`)}
            </DropdownMenuItem>
          );
        })}
        {hasRemove && regular.length > 0 && <DropdownMenuSeparator />}
        {hasRemove && (
          <DropdownMenuItem className="min-h-11 gap-2 text-destructive focus:text-destructive" onSelect={() => onAction("remove", target)}>
            <UserMinus className="h-4 w-4" aria-hidden />
            {t("team.remove")}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
