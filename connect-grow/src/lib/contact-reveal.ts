import i18n from "@/i18n";
import type { ContactChannel, Post, RevealChannel } from "@/api/types";
import { apiErrorCode, httpStatus, retryAfterSeconds } from "@/lib/errors";

/**
 * Moyens de contact affichables pour une offre. Une réponse sans `allowed_channels` (ancienne API)
 * ne propose que le message : on n'affiche jamais un moyen que le vendeur n'a pas accepté.
 */
export function allowedChannelsOf(post: Pick<Post, "allowed_channels">): ContactChannel[] {
  return post.allowed_channels ?? ["MESSAGE"];
}

// Garde-fou : seuls un lien téléphone ou un lien WhatsApp bien formés sont rendus (jamais javascript: ni autre schéma).
const TEL_URL = /^tel:\+?\d{6,15}$/;
const WHATSAPP_URL = /^https:\/\/wa\.me\/\d{6,15}(\?text=[^\s]*)?$/;

/** Lien à rendre pour un canal, ou null si la réponse du serveur est inattendue. */
export function revealLink(channel: RevealChannel, urls: { tel_url: string | null; whatsapp_url: string | null }): string | null {
  const url = channel === "CALL" ? urls.tel_url : urls.whatsapp_url;
  if (!url) return null;
  return (channel === "CALL" ? TEL_URL : WHATSAPP_URL).test(url) ? url : null;
}

/** « 45 secondes », « 12 minutes », « 3 heures » : délai arrondi par excès. */
export function formatWaitDelay(seconds: number | undefined): string {
  if (seconds === undefined) return i18n.t("reveal.delay.unknown");
  if (seconds < 60) return i18n.t("reveal.delay.seconds", { count: Math.max(1, Math.ceil(seconds)) });
  if (seconds < 3600) return i18n.t("reveal.delay.minutes", { count: Math.ceil(seconds / 60) });
  return i18n.t("reveal.delay.hours", { count: Math.ceil(seconds / 3600) });
}

export type RevealErrorKind =
  | "login" // 401 : invitation à se connecter
  | "unavailable" // le moyen ou l'offre n'est plus disponible : le message reste possible
  | "limit" // quota ou limite de débit : réessayer plus tard, ou écrire un message
  | "blocked" // propre annonce, compte restreint : rien à réessayer
  | "retry"; // erreur passagère (409, réseau, serveur) : « Réessayer »

export interface RevealErrorInfo {
  kind: RevealErrorKind;
  message: string;
}

/** Texte français et nature d'une erreur de POST interactions/contacts/reveal/ (ADR 0005 §5.4). */
export function revealErrorInfo(error: unknown): RevealErrorInfo {
  const t = i18n.t.bind(i18n);
  const status = httpStatus(error);
  const code = apiErrorCode(error);
  const delay = () => formatWaitDelay(retryAfterSeconds(error));

  if (status === undefined) return { kind: "retry", message: t("errors.network") };
  if (status === 401) return { kind: "login", message: t("reveal.errors.login") };
  if (status >= 500) return { kind: "retry", message: t("errors.server") };

  switch (code) {
    case "own_offer":
      return { kind: "blocked", message: t("reveal.errors.own_offer") };
    case "contact_restricted":
      return { kind: "blocked", message: t("reveal.errors.contact_restricted") };
    case "channel_not_allowed":
      return { kind: "unavailable", message: t("reveal.errors.channel_not_allowed") };
    case "offer_not_found":
      return { kind: "unavailable", message: t("reveal.errors.offer_not_found") };
    case "reveal_quota_account":
    case "reveal_quota_new_account":
    case "reveal_quota_ip":
      return { kind: "limit", message: t(`reveal.errors.${code}`, { delay: delay() }) };
    case "reveal_in_progress":
      return { kind: "retry", message: t("reveal.errors.reveal_in_progress", { delay: delay() }) };
    default:
      break;
  }
  if (status === 429) return { kind: "limit", message: t("reveal.errors.throttled", { delay: delay() }) };
  if (status === 409) return { kind: "retry", message: t("reveal.errors.reveal_in_progress", { delay: delay() }) };
  return { kind: "retry", message: t("reveal.errors.generic") };
}
