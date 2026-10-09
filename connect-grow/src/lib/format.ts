import { differenceInDays, differenceInHours, differenceInMonths, differenceInYears, formatDistanceToNowStrict } from "date-fns";
import { fr } from "date-fns/locale";
import type { Currency } from "@/api/types";

const LOCALE = "fr-FR";

const priceFormatters: Record<Currency, Intl.NumberFormat> = {
  USD: new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 }),
  CDF: new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 }),
};

const CURRENCY_SYMBOL: Record<Currency, string> = { USD: "$", CDF: "FC" };

/** 1250 USD → « 1 250 $ », 125000 CDF → « 125 000 FC ». */
export function formatPrice(amount: string | number, currency: Currency = "USD"): string {
  const value = typeof amount === "string" ? Number.parseFloat(amount) : amount;
  if (!Number.isFinite(value)) return "—";
  return `${priceFormatters[currency].format(value)} ${CURRENCY_SYMBOL[currency]}`;
}

const compactFormatter = new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 });

/** 1240 → « 1,2 k ». */
export function formatCount(value: number | undefined | null): string {
  return compactFormatter.format(value ?? 0);
}

/** « il y a 3 jours ». */
export function formatRelativeDate(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  if (Number.isNaN(d.getTime())) return "";
  return formatDistanceToNowStrict(d, { addSuffix: true, locale: fr });
}

/** Âge court pour les cartes étroites : « 3 h », « 2 j », « 5 mois », « 1 an ». */
export function formatShortAge(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const hours = differenceInHours(now, d);
  if (hours < 1) return "à l'instant";
  if (hours < 24) return `${hours} h`;
  const days = differenceInDays(now, d);
  if (days < 7) return `${days} j`;
  if (days < 30) return `${Math.floor(days / 7)} sem.`;
  const months = differenceInMonths(now, d);
  if (months < 12) return `${months} mois`;
  const years = differenceInYears(now, d);
  return `${years} an${years > 1 ? "s" : ""}`;
}

const ratingFormatter = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** 4.567 → « 4,6 ». */
export function formatRating(value: number): string {
  return ratingFormatter.format(value);
}

/** « Jean Mukendi » → « JM ». */
export function initials(name?: string | null): string {
  if (!name) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
