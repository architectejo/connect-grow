import type { ContactChannel, ContactSettings } from "@/api/types";
import i18n from "@/i18n";
import { describeApiError, isDenyCode } from "@/lib/api-errors";
import { apiErrorCode, apiErrorMessage, httpStatus } from "@/lib/errors";

/** Version du texte de consentement affichée par ce client (clé i18n `contactSettings.consent.<version>`). Provisoire (LEG-PRV). */
export const CONSENT_TEXT_VERSION = "2026-10-v1";

export const CONSENT_CHANNELS = ["CALL", "WHATSAPP"] as const;

const KNOWN_CODES = [
  "contact_phone_unverified",
  "consent_version_mismatch",
  "consent_text_required",
  "login_phone_unverified",
  "phone_invalid",
  "otp_invalid",
  "otp_expired",
  "otp_attempts_exceeded",
  "contact_phone_missing",
  "channel_unknown",
  "account_too_new",
  "channel_not_available",
  "login_phone_not_allowed",
] as const;

/**
 * Message français d'une erreur des réglages de contact. Le code machine prime sur le `detail` du serveur ; un refus
 * `DENY_*` (organisation suspendue, archivée, rôle insuffisant) passe par les textes communs des refus.
 */
export function contactSettingsErrorMessage(error: unknown, options: { inOrganization?: boolean } = {}): string {
  const code = apiErrorCode(error);
  if (code && (KNOWN_CODES as readonly string[]).includes(code)) return i18n.t(`contactSettings.errors.${code}`);
  if (httpStatus(error) === 403 && isDenyCode(code)) return describeApiError(error, options);
  return apiErrorMessage(error, i18n.t("contactSettings.errors.generic"));
}

/** Masque un numéro E.164 en ne gardant que les 4 derniers chiffres (« +243 ••• ••• 1234 »). Chaîne vide sans numéro. */
export function maskPhone(phone?: string | null): string {
  const digits = (phone ?? "").replace(/\D/g, "");
  if (digits.length < 8) return "";
  return `+${digits.slice(0, 3)} ••• ••• ${digits.slice(-4)}`;
}

const ALL_CHANNELS: ContactChannel[] = ["MESSAGE", "CALL", "WHATSAPP"];

/**
 * Canaux que le profil actif peut configurer (`available_channels`, ADR 0006 §17.1). Le client ne code pas l'état
 * de l'interrupteur des canaux téléphoniques des organisations : il suit la réponse du serveur. Clé absente
 * (réponse inattendue) : le message seul, seul canal toujours ouvert.
 */
export function availableChannels(settings: Pick<ContactSettings, "available_channels"> | undefined): ContactChannel[] {
  const offered = settings?.available_channels;
  return offered ? ALL_CHANNELS.filter((channel) => offered.includes(channel)) : ["MESSAGE"];
}

/** Vrai quand le serveur répond que le canal demandé n'est pas proposable : les réglages affichés sont à recharger. */
export const isChannelNotAvailable = (error: unknown) => apiErrorCode(error) === "channel_not_available";
