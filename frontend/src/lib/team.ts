import type { OrganizationMember, OrganizationRole } from "@/api/types";
import i18n from "@/i18n";
import { describeApiError, getApiErrorCode, isNetworkError } from "@/lib/api-errors";
import { apiErrorMessage, httpStatus, isRateLimited, retryAfterSeconds } from "@/lib/errors";

/** Actions possibles sur la ligne d'un membre (écran Équipe, L1-01). */
export type TeamAction = "changeRole" | "transfer" | "remove";

export const ORGANIZATION_ROLES: readonly OrganizationRole[] = ["OWNER", "ADMIN", "EDITOR", "ANALYST"];

interface Actor {
  role: OrganizationRole;
  capabilities: readonly string[];
}

/**
 * Actions proposées à l'acteur sur un membre. Le serveur reste l'arbitre : ce tri évite seulement de proposer une action
 * vouée au refus. Aucun blocage préventif sur le « dernier propriétaire » (`last_owner`, `last_effective_owner` : refus serveur).
 * Aucune notion de plan ou de paiement : seuls le rôle et les capacités comptent (règle 2).
 */
export function memberActions(actor: Actor, target: Pick<OrganizationMember, "role" | "is_self">): TeamAction[] {
  if (target.is_self) return [];
  const canRoles = actor.capabilities.includes("org.manage_roles");
  const canMembers = actor.capabilities.includes("org.manage_members");
  const actions: TeamAction[] = [];
  if (actor.role === "OWNER") {
    if (canRoles) actions.push("changeRole", "transfer");
    // Un propriétaire ne se retire pas : il faut d'abord le rétrograder (409 owner_must_be_demoted)
    if (canMembers && target.role !== "OWNER") actions.push("remove");
  } else if (actor.role === "ADMIN") {
    if (target.role === "OWNER") return [];
    if (canRoles) actions.push("changeRole");
    if (canMembers) actions.push("remove");
  }
  return actions;
}

/** Un administrateur voit la ligne d'un propriétaire sans menu : le texte « Réservé aux propriétaires » l'explique. */
export const isOwnersOnlyRow = (actor: Actor, target: Pick<OrganizationMember, "role" | "is_self">) =>
  actor.role === "ADMIN" && target.role === "OWNER" && !target.is_self;

/** Rôles que l'acteur peut attribuer (un administrateur n'attribue jamais OWNER). */
export const assignableRoles = (actorRole: OrganizationRole): OrganizationRole[] =>
  actorRole === "OWNER" ? [...ORGANIZATION_ROLES] : ORGANIZATION_ROLES.filter((role) => role !== "OWNER");

/** Mot de passe et confirmation exigés : promotion vers OWNER ou rétrogradation d'un OWNER (contrat §1.2). */
export const needsReauthentication = (currentRole: OrganizationRole, newRole: OrganizationRole) =>
  newRole !== currentRole && (newRole === "OWNER" || currentRole === "OWNER");

/** Issue d'un échec, telle que les fenêtres de l'écran Équipe la traitent. */
export type TeamFailure =
  /** 403 reauthentication_failed : erreur sous le champ mot de passe, la fenêtre reste ouverte. */
  | { kind: "reauth"; message: string }
  /** Le membre n'existe plus (404 member_not_found). */
  | { kind: "gone"; message: string }
  /** Refus d'autorisation (DENY_PERMISSION, DENY_RELATION) : fermeture et information. */
  | { kind: "denied"; message: string }
  /** 429 : bouton désactivé (`retryAfter` en secondes si le serveur l'indique). */
  | { kind: "rate"; message: string; retryAfter?: number }
  /** Erreur de champ DRF (`role`, `my_new_role`). */
  | { kind: "field"; field: string; message: string }
  /** Toute autre erreur : message dans la fenêtre, valeurs conservées. */
  | { kind: "form"; message: string };

const FIELDS = ["role", "my_new_role"] as const;

/** Classe une erreur d'API des trois routes d'équipe (texte tiré de l'i18n, jamais du `detail` du serveur pour les codes connus). */
export function classifyTeamError(error: unknown): TeamFailure {
  const t = i18n.t.bind(i18n);
  if (isNetworkError(error)) return { kind: "form", message: t("team.networkLost") };
  if (isRateLimited(error)) return { kind: "rate", message: t("team.retryLater"), retryAfter: retryAfterSeconds(error) };
  const status = httpStatus(error);
  const code = getApiErrorCode(error);
  if (code === "reauthentication_failed") return { kind: "reauth", message: t("errors.code.reauthentication_failed") };
  if (code === "member_not_found") return { kind: "gone", message: t("team.alreadyGone") };
  if (status === 403 && (code === "DENY_PERMISSION" || code === "DENY_RELATION")) {
    return { kind: "denied", message: describeApiError(error, { inOrganization: true }) };
  }
  if (status === 400 && !code) {
    const data = (error as { response?: { data?: Record<string, unknown> } }).response?.data;
    const field = FIELDS.find((name) => Array.isArray(data?.[name]));
    if (field) return { kind: "field", field, message: apiErrorMessage(error) };
  }
  return { kind: "form", message: describeApiError(error, { inOrganization: true, demote: true }) };
}

/** Case de confirmation et mot de passe saisis dans une fenêtre sensible (état local, jamais persisté). */
export interface SensitiveConfirmValue {
  confirmed: boolean;
  password: string;
}

/** La confirmation est complète : case cochée et mot de passe saisi. */
export const isSensitiveConfirmComplete = (value: SensitiveConfirmValue) => value.confirmed && value.password.length > 0;
