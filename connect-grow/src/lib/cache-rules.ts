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
  // Espace d'une organisation (internal, kyc, verification, limits, archive, leave), prestataire et profils : privés
  if (/\/accounts\/(organizations\/[^/]+|provider|contexts)(\/|$)/.test(url.pathname)) return false;
  // Lectures publiques : offres, profils publics de vendeurs, liste (seule) des organisations
  return (
    /\/api\/v1\/marketplace\/(posts|sellers)\//.test(url.pathname) || /\/api\/v1\/accounts\/organizations\/$/.test(url.pathname)
  );
}

/**
 * Routes qui portent ou listent des numéros de contact (ADR 0005 §5.4 et §5.5) : toujours réseau seul
 * (stratégie NetworkOnly). Workbox n'enregistre cette règle que pour les requêtes GET (méthode par défaut) :
 * le POST de révélation n'est jamais intercepté ni mis en cache par le service worker, il part directement au réseau.
 * Même contrainte d'autonomie que ci-dessus.
 */
export function isContactRevealRequest({ url }: { url: URL }): boolean {
  return /\/api\/(v\d+\/)?interactions\/contacts\/(reveal|reveals\/received)\/?$/.test(url.pathname);
}

/**
 * Liste des profils du compte (`accounts/contexts/`) : rôles et capacités, jamais mis en cache hors ligne
 * (le serveur répond déjà `Cache-Control: private, no-store`). Réseau seul. Même contrainte d'autonomie que ci-dessus.
 */
export function isContextsRequest({ url }: { url: URL }): boolean {
  return /\/api\/(v\d+\/)?accounts\/contexts\/?$/.test(url.pathname);
}

/**
 * Espace privé d'une organisation et profil prestataire : `organizations/<id>/…` (internal, kyc, verification, archive,
 * leave, limits), `provider/…` et `kyc/…`. Rôles, NIF, état des pièces : jamais en cache hors ligne (réseau seul).
 * La liste PUBLIQUE `organizations/` n'en fait pas partie. Même contrainte d'autonomie que ci-dessus.
 */
export function isSensitiveIdentityRequest({ url }: { url: URL }): boolean {
  return /\/api\/(v\d+\/)?accounts\/(organizations\/[^/]+|provider|kyc)(\/|$)/.test(url.pathname);
}
