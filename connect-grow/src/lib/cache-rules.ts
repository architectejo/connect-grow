/**
 * Règle de mise en cache PWA « api-annonces » : lectures publiques uniquement.
 *
 * IMPORTANT : vite-plugin-pwa (Workbox generateSW) sérialise cette fonction dans le service worker
 * via toString(). Elle doit donc rester autonome : aucune référence à un import, une constante
 * ou une fonction extérieure.
 */
export function isCacheableApiContent({ url, request }: { url: URL; request: Request }): boolean {
  if (request.method !== "GET") return false;
  if (request.headers.has("Authorization")) return false;
  if (url.searchParams.has("my_posts")) return false;
  if (/\/posts\/(trash|mine)\//.test(url.pathname)) return false;
  // Données personnelles : pièces KYC, messages, contacts, avis, notifications (jamais en cache)
  if (/\/(accounts\/kyc|interactions)\//.test(url.pathname)) return false;
  return /\/api\/(v1\/)?(marketplace\/posts|accounts\/businesses)\//.test(url.pathname);
}
