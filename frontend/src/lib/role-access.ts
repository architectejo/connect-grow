/**
 * Traduction des codes de capacité d'un rôle en « accès » lisibles, regroupés par thème (spec D2 §9.2, contrat §7.4.4).
 * La table est fixe ; un code inconnu n'est jamais masqué : il est compté dans `others` (« et N autre(s) accès »).
 * `billing.*` est un accès de rôle, jamais un droit commercial ni une promesse de plan (règle 2).
 */

export const ACCESS_GROUPS = ["organization", "team", "offers", "reviews", "contact", "messages", "stats", "billing"] as const;
export type AccessGroup = (typeof ACCESS_GROUPS)[number];

/** Code de capacité → thème. L'ordre dans chaque thème est celui de la table de la spec. */
export const CAPABILITY_GROUPS: Readonly<Record<string, AccessGroup>> = {
  "org.view_internal": "organization",
  "org.edit_profile": "organization",
  "org.verification_submit": "organization",
  "org.archive": "organization",
  "org.leave": "organization",
  "org.manage_members": "team",
  "org.manage_roles": "team",
  "offer.view_internal": "offers",
  "offer.publish": "offers",
  "offer.edit": "offers",
  "offer.delete": "offers",
  "review.reply": "reviews",
  "contact.view_requesters": "contact",
  "contact.manage_channels": "contact",
  "message.reply": "messages",
  "stats.view": "stats",
  "billing.view": "billing",
  "billing.purchase": "billing",
};

const ORDER = Object.keys(CAPABILITY_GROUPS);

/** Clé i18n du libellé d'une capacité connue (`access.cap.org_view_internal`). */
export const capabilityLabelKey = (code: string) => `access.cap.${code.replace(/\./g, "_")}`;

export interface AccessGroupItems {
  group: AccessGroup;
  codes: string[];
}

export interface GroupedCapabilities {
  groups: AccessGroupItems[];
  /** Nombre de codes inconnus (non traduits) : jamais masqués, comptés en fin de liste. */
  others: number;
}

/** Regroupe les codes par thème (ordre des thèmes et des codes fixé par la table), doublons retirés. */
export function groupCapabilities(codes: readonly string[]): GroupedCapabilities {
  const unique = Array.from(new Set(codes));
  const known = unique.filter((code) => code in CAPABILITY_GROUPS).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
  const groups = ACCESS_GROUPS.map((group) => ({ group, codes: known.filter((code) => CAPABILITY_GROUPS[code] === group) })).filter(
    (entry) => entry.codes.length > 0,
  );
  return { groups, others: unique.length - known.length };
}
