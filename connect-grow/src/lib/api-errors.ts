import axios from "axios";
import i18n from "@/i18n";
import { apiErrorCode, apiErrorMessage, httpStatus, isRateLimited, rateLimitMessage } from "@/lib/errors";
import type { LostReason } from "@/lib/active-context";

/** Refus d'autorisation (403) du serveur (ADR 0006 §9). */
export const DENY_CODES = ["DENY_CONTEXT", "DENY_RELATION", "DENY_PERMISSION", "DENY_SECURITY", "DENY_OBJECT_STATE"] as const;
export type DenyCode = (typeof DENY_CODES)[number];

/** Les quatre codes qui peuvent signifier que le profil actif n'est plus utilisable (règle 9.1). */
export const CONTEXT_DENY_CODES = ["DENY_CONTEXT", "DENY_RELATION", "DENY_SECURITY", "DENY_OBJECT_STATE"] as const;
export type ContextDenyCode = (typeof CONTEXT_DENY_CODES)[number];

/** Codes métier de l'ADR 0006 (409/403/400) avec un texte dédié. */
const BUSINESS_CODES = [
  "last_owner",
  "organization_limit_reached",
  "phone_verification_required",
  "name_locked_by_verification",
  "nif_locked_by_verification",
  "seller_not_settable",
  "seller_contact_unavailable",
  "document_already_validated",
  "document_validated",
  "document_type_not_required",
  "document_limit_reached",
  "too_many_categories",
  "invalid_name",
  "invalid_logo",
  "provider_not_found",
] as const;
export type BusinessCode = (typeof BUSINESS_CODES)[number];

export const getApiErrorCode = apiErrorCode;

export const isDenyCode = (code: unknown): code is DenyCode => typeof code === "string" && (DENY_CODES as readonly string[]).includes(code);
export const isContextDenyCode = (code: unknown): code is ContextDenyCode =>
  typeof code === "string" && (CONTEXT_DENY_CODES as readonly string[]).includes(code);
const isBusinessCode = (code: unknown): code is BusinessCode => typeof code === "string" && (BUSINESS_CODES as readonly string[]).includes(code);

/** Erreur sans réponse du serveur (réseau coupé, délai dépassé). */
export const isNetworkError = (error: unknown) => axios.isAxiosError(error) && !error.response;

/** Raison de perte du profil correspondant à un code `DENY_*`. */
export function lostReasonFor(code: ContextDenyCode): LostReason {
  return code.replace("DENY_", "") as LostReason;
}

/** Clé i18n du message « profil perdu » (alerte persistante). */
export function lostMessageKey(reason: LostReason): string {
  return reason === "left" || reason === "archived" ? `errors.lost.${reason}` : `errors.deny.${reason}.lost`;
}

export interface DescribeOptions {
  /** Refus de permission : le profil actif est une organisation (texte « demandez à un propriétaire »). */
  inOrganization?: boolean;
  /** `last_owner` lors d'une rétrogradation ou d'un retrait (écran d'équipe, L1-01). */
  demote?: boolean;
  /** Texte de repli quand le code est inconnu. */
  fallback?: string;
}

/**
 * Texte français d'une erreur d'API, tiré des clés i18n et non du `detail` du serveur (sans nom de profil).
 * Pour un refus qui concerne le profil actif, c'est le texte « action refusée », local à l'action : la décision
 * de quitter le profil est prise ailleurs, d'après la liste de `contexts/` (règle 9.1).
 */
export function describeApiError(error: unknown, options: DescribeOptions = {}): string {
  const t = i18n.t.bind(i18n);
  if (isNetworkError(error)) return t("errors.network");
  if (isRateLimited(error)) return rateLimitMessage(error);
  const code = apiErrorCode(error);
  if (httpStatus(error) === 403 && isDenyCode(code)) {
    if (code === "DENY_PERMISSION") return t(options.inOrganization ? "errors.deny.PERMISSION.org" : "errors.deny.PERMISSION.generic");
    return t(`errors.deny.${code.replace("DENY_", "")}.action`);
  }
  if (isBusinessCode(code)) {
    return t(code === "last_owner" && options.demote ? "errors.code.last_owner_demote" : `errors.code.${code}`);
  }
  return apiErrorMessage(error, options.fallback);
}

/** Texte d'un refus d'accès à l'espace d'une organisation (clés `org.denied.*`), ou null si ce n'est pas un refus. */
export function organizationDeniedKey(error: unknown): string | null {
  if (httpStatus(error) !== 403) return null;
  switch (apiErrorCode(error)) {
    case "DENY_SECURITY":
      return "org.denied.security";
    case "DENY_OBJECT_STATE":
      return "org.denied.archived";
    case "DENY_RELATION":
    case "DENY_CONTEXT":
    case "DENY_PERMISSION":
      return "org.denied.relation";
    default:
      return null;
  }
}
