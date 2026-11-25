import type { OrganizationInvitation } from "@/api/types";
import i18n from "@/i18n";
import { describeApiError, getApiErrorCode, isNetworkError } from "@/lib/api-errors";
import { InvitationTokenMissingError } from "@/lib/invitation-token";
import { httpStatus, isRateLimited, retryAfterSeconds } from "@/lib/errors";

/** Longueur maximale de l'étiquette d'une invitation (contrat §2.1) : verrou de saisie, le serveur reste l'arbitre. */
export const INVITATION_LABEL_MAX = 60;

/** Une invitation n'est annulable que si elle est encore en attente : `EXPIRED` (statut effectif) ou échue, jamais. */
export function isInvitationExpired(invitation: Pick<OrganizationInvitation, "status" | "expires_at">, now: number = Date.now()): boolean {
  if (invitation.status !== "PENDING") return true;
  const expires = Date.parse(invitation.expires_at);
  return !Number.isNaN(expires) && expires <= now;
}

/** Issue d'un échec de création d'invitation, telle que `InviteDialog` la traite. */
export type CreateInvitationFailure =
  /** Réseau coupé sans réponse : l'invitation a peut-être été créée, aucune relance automatique. */
  | { kind: "network"; message: string }
  /** 429 : bouton désactivé (`retryAfter` en secondes si le serveur l'indique). */
  | { kind: "rate"; message: string; retryAfter?: number }
  /** Erreur de champ DRF : sous le champ concerné. */
  | { kind: "field"; field: "label" | "role"; message: string }
  /** 403 DENY_PERMISSION : fermeture et information. */
  | { kind: "denied"; message: string }
  | { kind: "form"; message: string };

export function classifyCreateInvitationError(error: unknown): CreateInvitationFailure {
  const t = i18n.t.bind(i18n);
  if (isNetworkError(error)) return { kind: "network", message: t("team.invite.errNetwork") };
  if (isRateLimited(error)) {
    const retryAfter = retryAfterSeconds(error);
    const message = retryAfter ? t("team.invite.errRateIn", { minutes: Math.max(1, Math.ceil(retryAfter / 60)) }) : t("team.invite.errRate");
    return { kind: "rate", message, retryAfter };
  }
  const status = httpStatus(error);
  const code = getApiErrorCode(error);
  if (code === "invitation_limit_reached") return { kind: "form", message: t("team.invite.errLimit") };
  if (code === "invitation_role_not_allowed") return { kind: "field", field: "role", message: t("team.invite.errRole") };
  if (status === 403 && code === "DENY_PERMISSION") return { kind: "denied", message: describeApiError(error, { inOrganization: true }) };
  if (status === 400 && !code) {
    const data = (error as { response?: { data?: Record<string, unknown> } }).response?.data;
    if (Array.isArray(data?.role)) return { kind: "field", field: "role", message: t("team.invite.errRole") };
    if (Array.isArray(data?.label)) {
      // Message de champ du serveur s'il en donne un ; sinon le texte de la spec (« Cette étiquette est trop longue. »)
      const first = (data.label as unknown[]).find((item): item is string => typeof item === "string" && item.trim().length > 0);
      return { kind: "field", field: "label", message: first ?? t("team.invite.errLabelTooLong") };
    }
  }
  return { kind: "form", message: describeApiError(error, { inOrganization: true }) };
}

/** Issue d'un échec d'aperçu, d'acceptation ou de refus, telle que la page d'acceptation l'affiche (spec E15 §4.5). */
export type InvitationFailureKind =
  | "invalid"
  /** Plus aucun jeton utilisable dans l'onglet (expiré après 60 minutes, lié à un autre compte) : « Lien incomplet ». */
  | "missing"
  | "phone"
  | "limit"
  | "member"
  | "security"
  /** 401 : session expirée. `clearSession` efface alors le jeton (audit S2) : la page affiche « Lien incomplet » (lien à rouvrir). */
  | "unauthenticated"
  | "rate"
  | "network"
  | "generic";

export interface InvitationFailure {
  kind: InvitationFailureKind;
  /** Secondes d'attente lues dans `Retry-After` (429). */
  retryAfter?: number;
}

/**
 * Classe une erreur des routes d'échange. Aucun texte du serveur n'est repris : les messages viennent de l'i18n et ne disent
 * jamais pourquoi un jeton est invalide (réponse uniforme, aucun oracle). Le jeton n'apparaît nulle part dans le résultat.
 */
export function classifyInvitationError(error: unknown): InvitationFailure {
  if (error instanceof InvitationTokenMissingError) return { kind: "missing" };
  if (isNetworkError(error)) return { kind: "network" };
  if (isRateLimited(error)) return { kind: "rate", retryAfter: retryAfterSeconds(error) };
  const status = httpStatus(error);
  const code = getApiErrorCode(error);
  if (status === 401) return { kind: "unauthenticated" };
  if (code === "invitation_invalid") return { kind: "invalid" };
  if (code === "phone_verification_required") return { kind: "phone" };
  if (code === "organization_limit_reached") return { kind: "limit" };
  if (code === "already_member") return { kind: "member" };
  if (status === 403 && (code === "DENY_SECURITY" || code === "DENY_OBJECT_STATE" || code === "DENY_RELATION")) return { kind: "security" };
  // `400 {"token": [...]}` : traité comme un jeton invalide
  if (status === 400) {
    const data = (error as { response?: { data?: Record<string, unknown> } }).response?.data;
    if (Array.isArray(data?.token)) return { kind: "invalid" };
  }
  return { kind: "generic" };
}

/** Le jeton est à supprimer du stockage après cet échec (spec E15 §4.2 point 6) ; il est conservé sur les autres. */
export const clearsTokenOnFailure = (kind: InvitationFailureKind) => kind === "invalid" || kind === "member";
