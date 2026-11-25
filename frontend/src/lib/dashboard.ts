import { getApiErrorCode } from "@/lib/api-errors";
import { httpStatus } from "@/lib/errors";

/** Capacité qui ouvre les statistiques du tableau de bord (contrat L1-01 §7.1 : le rôle Membre ne l'a pas). */
export const DASHBOARD_CAPABILITY = "stats.view";
/** Capacité qui ouvre « Mes annonces » du profil actif (`my_posts=true`, `offer.view_internal`). */
export const MY_POSTS_CAPABILITY = "offer.view_internal";

interface ActiveCapabilities {
  confirmed: boolean;
  capabilities: readonly string[];
}

/**
 * Le profil actif, CONFIRMÉ par le serveur, n'a pas cette capacité. Tant que le serveur n'a pas répondu, on ne
 * conclut rien (faux) : la requête part et un refus 403 `DENY_PERMISSION` est traité à la réception.
 * Le masquage n'est pas le contrôle : le serveur reste le juge (règle 2).
 */
export const lacksCapability = (active: ActiveCapabilities, capability: string): boolean =>
  active.confirmed && !active.capabilities.includes(capability);

/** Refus d'autorisation lié au rôle (403 `DENY_PERMISSION`) : un état explicite, jamais une erreur à réessayer. */
export const isPermissionDenied = (error: unknown): boolean => httpStatus(error) === 403 && getApiErrorCode(error) === "DENY_PERMISSION";
