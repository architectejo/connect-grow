import { toast } from "sonner";

/** « 081 234 5678 » ou « +243 81 234 5678 » → « 243812345678 » (format international sans +). */
export function toInternationalDigits(phone?: string | null): string | null {
  if (!phone) return null;
  let digits = phone.replace(/\D/g, "");
  if (digits.startsWith("00")) digits = digits.slice(2);
  if (digits.startsWith("0")) digits = `243${digits.slice(1)}`;
  if (digits.length === 9) digits = `243${digits}`;
  return digits.length >= 11 ? digits : null;
}

export function telLink(phone?: string | null): string | null {
  const digits = toInternationalDigits(phone);
  return digits ? `tel:+${digits}` : null;
}

export function whatsappLink(phone?: string | null, message?: string): string | null {
  const digits = toInternationalDigits(phone);
  if (!digits) return null;
  return `https://wa.me/${digits}${message ? `?text=${encodeURIComponent(message)}` : ""}`;
}

/** Partage natif sur mobile ; sinon copie du lien dans le presse-papiers. */
export async function shareLink({ title, text, url }: { title: string; text?: string; url: string }) {
  if (navigator.share) {
    try {
      await navigator.share({ title, text, url });
      return;
    } catch (error) {
      if ((error as DOMException)?.name === "AbortError") return;
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    toast.success("Lien copié dans le presse-papiers.");
  } catch {
    toast.error("Impossible de copier le lien.");
  }
}
