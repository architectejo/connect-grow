import i18n from "@/i18n";

type ErrorResponse = { status?: number; data?: unknown; headers?: Record<string, unknown> | { get?: (name: string) => unknown } };

const responseOf = (error: unknown): ErrorResponse | undefined => (error as { response?: ErrorResponse } | null)?.response;

/** Code HTTP d'une erreur axios, ou undefined (réseau coupé, erreur non HTTP). */
export function httpStatus(error: unknown): number | undefined {
  return responseOf(error)?.status;
}

export const isRateLimited = (error: unknown) => httpStatus(error) === 429;

function readHeader(headers: ErrorResponse["headers"], name: string): string | undefined {
  if (!headers) return undefined;
  const raw =
    typeof (headers as { get?: unknown }).get === "function"
      ? (headers as { get: (n: string) => unknown }).get(name)
      : (headers as Record<string, unknown>)[name] ?? (headers as Record<string, unknown>)[name.toLowerCase()];
  return raw === undefined || raw === null ? undefined : String(raw);
}

/**
 * Délai d'attente (en secondes) demandé par le serveur lors d'un 429.
 * Lit l'en-tête Retry-After (secondes ou date HTTP) ; à défaut, le délai cité dans le corps DRF
 * (« Expected available in N seconds »). Undefined si rien d'exploitable.
 */
export function retryAfterSeconds(error: unknown, now: number = Date.now()): number | undefined {
  const response = responseOf(error);
  if (!response) return undefined;

  const header = readHeader(response.headers, "Retry-After")?.trim();
  if (header) {
    if (/^\d+$/.test(header)) return Math.max(1, Number(header));
    const date = Date.parse(header);
    if (!Number.isNaN(date)) return Math.max(1, Math.ceil((date - now) / 1000));
  }

  const detail = (response.data as { detail?: unknown } | null)?.detail;
  const match = typeof detail === "string" ? /(\d+)\s*second/i.exec(detail) : null;
  return match ? Math.max(1, Number(match[1])) : undefined;
}

/** « Trop de tentatives, réessayez dans N secondes » (texte i18n, jamais le message anglais de DRF). */
export function rateLimitMessage(error: unknown): string {
  const seconds = retryAfterSeconds(error);
  return seconds === undefined ? i18n.t("errors.tooManyAttemptsNoDelay") : i18n.t("errors.tooManyAttempts", { count: seconds });
}

const MAX_MESSAGE_LENGTH = 200;
const limitLength = (text: string) => (text.length > MAX_MESSAGE_LENGTH ? `${text.slice(0, MAX_MESSAGE_LENGTH - 1)}…` : text);

/**
 * Premier message d'erreur lisible d'une réponse DRF.
 * Un 429 donne toujours le message de délai ; sans réponse (réseau), le message de connexion.
 */
export function apiErrorMessage(error: unknown, fallback?: string): string {
  const response = responseOf(error);
  if (response?.status === 429) return rateLimitMessage(error);
  const fallbackText = fallback ?? i18n.t("errors.generic");
  // 5xx : le corps peut contenir une trace ou du HTML serveur, il n'est jamais affiché
  if (response?.status !== undefined && response.status >= 500) return i18n.t("errors.server");
  const data = response?.data;
  // 404 : l'API répond aussi 404 (et non 403) pour l'action d'un propriétaire sur l'offre d'autrui.
  // Un message métier explicite (clé `error`) reste prioritaire sur le texte générique de DRF.
  if (response?.status === 404 && typeof (data as { error?: unknown } | null)?.error !== "string") return i18n.t("errors.notFound");
  if (!data || typeof data !== "object") return fallbackText;
  const record = data as Record<string, unknown>;
  const first = record.non_field_errors ?? record.detail ?? record.error ?? Object.values(record)[0];
  if (Array.isArray(first)) return first.length ? limitLength(String(first[0])) : fallbackText;
  return typeof first === "string" ? limitLength(first) : fallbackText;
}

/** Les erreurs réseau, 429 et 5xx ne se règlent pas en réessayant tout de suite : pas de relance automatique. */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  const status = httpStatus(error);
  if (status !== undefined && status >= 400 && status < 500) return false; // 4xx : la requête est en cause, ou le débit limité
  return failureCount < 1;
}
