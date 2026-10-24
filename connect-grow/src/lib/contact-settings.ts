import type { ContactChannel, ContactSettings, ContextType } from "@/api/types";
import i18n from "@/i18n";
import { apiErrorCode, apiErrorMessage } from "@/lib/errors";

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
] as const;

/** Message français d'une erreur `{detail, code}` des réglages de contact ; le code machine prime sur le `detail` du serveur. */
export function contactSettingsErrorMessage(error: unknown): string {
  const code = apiErrorCode(error);
  if (code && (KNOWN_CODES as readonly string[]).includes(code)) return i18n.t(`contactSettings.errors.${code}`);
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
 * de l'interrupteur des canaux téléphoniques des organisations : il suit la réponse du serveur. Clé absente :
 * profil personnel ou prestataire, les trois canaux ; organisation, le message seul (repli prudent).
 */
export function availableChannels(settings: Pick<ContactSettings, "available_channels"> | undefined, contextType: ContextType): ContactChannel[] {
  if (settings?.available_channels) return ALL_CHANNELS.filter((channel) => settings.available_channels?.includes(channel));
  return contextType === "ORGANIZATION" ? ["MESSAGE"] : ALL_CHANNELS;
}
