import { POST_DRAFT_KEY } from "@/lib/tokens";

interface StoredDraft<T> {
  userId: string;
  values: T;
}

/** Brouillon d'annonce de CET utilisateur ; un brouillon d'un autre compte (ou ancien format sans propriétaire) est ignoré. */
export function readDraft<T>(userId: string | undefined): T | null {
  if (!userId) return null;
  try {
    const raw = localStorage.getItem(POST_DRAFT_KEY);
    const stored = raw ? (JSON.parse(raw) as Partial<StoredDraft<T>> | null) : null;
    return stored && stored.userId === userId && stored.values ? stored.values : null;
  } catch {
    return null;
  }
}

export function writeDraft<T>(userId: string | undefined, values: T): void {
  if (!userId) return;
  try {
    localStorage.setItem(POST_DRAFT_KEY, JSON.stringify({ userId, values } satisfies StoredDraft<T>));
  } catch {
    /* stockage indisponible */
  }
}

export function clearDraft(): void {
  try {
    localStorage.removeItem(POST_DRAFT_KEY);
  } catch {
    /* stockage indisponible */
  }
}
