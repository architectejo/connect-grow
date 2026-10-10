/**
 * Règle de mise en cache PWA « api-annonces-v2 » : lectures publiques uniquement.
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

/**
 * Routes qui portent ou listent des numéros de contact (ADR 0005 §5.4 et §5.5) : toujours réseau seul
 * (stratégie NetworkOnly). Workbox n'enregistre cette règle que pour les requêtes GET (méthode par défaut) :
 * le POST de révélation n'est jamais intercepté ni mis en cache par le service worker, il part directement au réseau.
 * Même contrainte d'autonomie que ci-dessus.
 */
export function isContactRevealRequest({ url }: { url: URL }): boolean {
  return /\/api\/(v1\/)?interactions\/contacts\/(reveal|reveals\/received)\/?$/.test(url.pathname);
}
