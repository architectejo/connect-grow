import { formatDuration, intervalToDuration } from "date-fns";
import { fr } from "date-fns/locale";
import i18n from "@/i18n";
import { apiErrorCode, apiErrorMessage, httpStatus, retryAfterSeconds } from "@/lib/errors";

const KNOWN_CODES = [
  "not_authenticated",
  "offer_not_found",
  "own_offer",
  "not_eligible",
  "contact_rejected",
  "review_too_early",
  "account_too_new",
  "report_already_rejected",
  "already_responded",
  "report_closed",
  "already_reviewed",
  "review_recently_deleted",
  "offer_unavailable",
  "edit_window_closed",
  "review_locked",
  "review_locked_after_reply",
  "not_author",
  "not_seller",
  "already_replied",
  "duplicate_report",
  "invalid_reason",
] as const;

/** « 3 heures », « 45 minutes » à partir d'un délai en secondes. */
export function humanizeSeconds(seconds: number): string {
  const duration = intervalToDuration({ start: 0, end: seconds * 1000 });
  const text = formatDuration(duration, { locale: fr, format: seconds >= 3600 ? ["days", "hours"] : seconds >= 60 ? ["minutes"] : ["seconds"] });
  return text || formatDuration({ seconds }, { locale: fr });
}

/**
 * Message en français d'une erreur de l'API des avis. Le front se fonde sur `code` (ADR 0004 §7.2),
 * jamais sur le texte du serveur. Les erreurs de champs (400) et les cas inconnus passent par apiErrorMessage.
 */
export function reviewErrorMessage(error: unknown, action?: "delete"): string {
  const code = apiErrorCode(error);

  // DELETE refusé alors que PATCH reste permis : l'explication porte sur la suppression seulement
  if (action === "delete" && code === "review_locked") return i18n.t("reviews.errors.review_locked_delete");

  if (httpStatus(error) === 429 && code === "report_daily_limit") {
    const seconds = retryAfterSeconds(error);
    return seconds === undefined
      ? i18n.t("reviews.errors.report_daily_limit")
      : i18n.t("reviews.errors.report_daily_limit_retry", { duration: humanizeSeconds(seconds) });
  }

  if (httpStatus(error) === 429 && code === "daily_limit") {
    const seconds = retryAfterSeconds(error);
    return seconds === undefined
      ? i18n.t("reviews.errors.daily_limit")
      : i18n.t("reviews.errors.daily_limit_retry", { duration: humanizeSeconds(seconds) });
  }
  // « throttled » (10/h) et tout autre 429 : message de délai générique
  if (code && (KNOWN_CODES as readonly string[]).includes(code)) return i18n.t(`reviews.errors.${code}`);
  return apiErrorMessage(error);
}
