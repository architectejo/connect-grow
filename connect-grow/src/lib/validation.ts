import { z } from "zod";

// Numéros congolais : +243 suivi de 9 chiffres (CDC 2.3), ex. +243 81 234 5678.
export const PHONE_PREFIX = "+243";

/** Chiffres saisis après +243 : on tolère le 0 initial (« 0812345678 ») et les espaces. */
export function normalizeLocalPhone(input: string): string {
  let digits = input.replace(/\D/g, "");
  if (digits.startsWith("243")) digits = digits.slice(3);
  if (digits.startsWith("0")) digits = digits.slice(1);
  return digits.slice(0, 9);
}

export const toE164 = (localDigits: string) => `${PHONE_PREFIX}${localDigits}`;

/** « 812345678 » → « 81 234 5678 » pour l'affichage. */
export function formatLocalPhone(digits: string): string {
  return [digits.slice(0, 2), digits.slice(2, 5), digits.slice(5, 9)].filter(Boolean).join(" ");
}

export const localPhoneSchema = z
  .string()
  .min(1, "Saisissez votre numéro.")
  .regex(/^\d{9}$/, "Le numéro doit compter 9 chiffres après +243.");

export const emailSchema = z.string().trim().min(1, "Saisissez votre adresse e-mail.").email("Adresse e-mail invalide.");

export const PASSWORD_MIN = 8;
export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN, `Au moins ${PASSWORD_MIN} caractères.`)
  .regex(/[A-Za-z]/, "Au moins une lettre.")
  .regex(/\d/, "Au moins un chiffre.");

export const otpSchema = z.string().regex(/^\d{6}$/, "Le code compte 6 chiffres.");

/** Robustesse de 0 à 4, pour la jauge sous le champ mot de passe. */
export function passwordStrength(password: string): 0 | 1 | 2 | 3 | 4 {
  if (!password) return 0;
  let score = 0;
  if (password.length >= PASSWORD_MIN) score++;
  if (/[A-Za-z]/.test(password) && /\d/.test(password)) score++;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password) || password.length >= 12) score++;
  return score as 0 | 1 | 2 | 3 | 4;
}

/**
 * Erreurs d'un formulaire renvoyées par DRF ({ champ: ["message"] } ou { error: "…" })
 * ramenées à un message par champ, plus un message général.
 */
export function parseApiErrors(error: unknown): { fields: Record<string, string>; general?: string } {
  const response = (error as { response?: { data?: unknown; status?: number } })?.response;
  if (!response) return { fields: {}, general: "Connexion impossible. Vérifiez votre réseau puis réessayez." };
  if (response.status === 429) return { fields: {}, general: "Trop de tentatives. Patientez un peu avant de réessayer." };

  const data = response.data;
  if (!data || typeof data !== "object") return { fields: {}, general: "Une erreur est survenue. Réessayez." };

  const fields: Record<string, string> = {};
  let general: string | undefined;
  for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
    const message = Array.isArray(value) ? String(value[0]) : typeof value === "string" ? value : undefined;
    if (!message) continue;
    if (key === "non_field_errors" || key === "detail" || key === "error") general = message;
    else fields[key] = message;
  }
  return { fields, general };
}
