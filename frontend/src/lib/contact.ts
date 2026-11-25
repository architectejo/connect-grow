import { toast } from "sonner";
import i18n from "@/i18n";

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
    toast.success(i18n.t("feedback.linkCopied"));
  } catch {
    toast.error(i18n.t("feedback.linkCopyFailed"));
  }
}
