import { MEDIA_BASE_URL } from "@/config/env";

/**
 * Transforme un chemin média renvoyé par l'API (/media/posts/x.webp) en URL absolue.
 * Les URL déjà absolues (CDN, blob:, data:) sont renvoyées telles quelles.
 */
export function mediaUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  if (/^(https?:|blob:|data:)/.test(path)) return path;
  return `${MEDIA_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;
}
