import type { AvailableContext } from "@/api/types";

/** Mémorisation locale de la fermeture du message « Votre compte entreprise est devenu une organisation » (E14). */
const PREFIX = "connecte.legacyNotice.";

export const legacyNoticeKey = (organizationId: string) => `${PREFIX}${organizationId}`;

export function isLegacyNoticeDismissed(organizationId: string): boolean {
  try {
    return localStorage.getItem(legacyNoticeKey(organizationId)) === "1";
  } catch {
    return false;
  }
}

export function dismissLegacyNotice(organizationId: string): void {
  try {
    localStorage.setItem(legacyNoticeKey(organizationId), "1");
  } catch {
    /* navigation privée : le message reviendra à la prochaine visite */
  }
}

/** Efface les mémorisations (déconnexion : un autre compte du même appareil doit revoir ses propres messages). */
export function clearLegacyNotices(): void {
  try {
    for (const key of Object.keys(localStorage)) if (key.startsWith(PREFIX)) localStorage.removeItem(key);
  } catch {
    /* rien à effacer */
  }
}

/** Organisations issues d'un ancien compte entreprise (`migrated_from_business`, clé absente = faux). */
export const migratedOrganizations = (contexts: AvailableContext[]) =>
  contexts.filter((c) => c.type === "ORGANIZATION" && c.migrated_from_business === true);
