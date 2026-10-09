import { toast } from "sonner";

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
