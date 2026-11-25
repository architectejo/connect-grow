import { Building2, CalendarDays, HeartHandshake, Store, type LucideIcon } from "lucide-react";
import { z } from "zod";
import type { City, OrganizationInput, OrganizationInternal, OrganizationLimits, OrganizationType, Uuid } from "@/api/types";

/** Types d'organisation proposés à la création (le serveur reste la référence). */
export const ORG_TYPES: { value: OrganizationType; icon: LucideIcon }[] = [
  { value: "ENTREPRISE", icon: Building2 },
  { value: "BOUTIQUE", icon: Store },
  { value: "ONG", icon: HeartHandshake },
  { value: "ORGANISATEUR_EVENEMENTS", icon: CalendarDays },
];

/** Valeurs de repli tant que `organizations/limits/` n'a pas répondu : le serveur valide toujours (règle 11). */
export const FALLBACK_LIMITS: OrganizationLimits = {
  max_categories_per_context: 5,
  max_organizations_per_account: 10,
  name_min_length: 2,
  name_max_length: 255,
  description_max_length: 2000,
};

export const NIF_MAX_LENGTH = 50;

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface OrganizationFormValues {
  org_type: OrganizationType | "";
  name: string;
  description: string;
  commune_id: string;
  nif: string;
  category_ids: Uuid[];
}

/** Schéma du formulaire de création et de modification, aligné sur les limites lues sur le serveur. */
export function organizationSchema(limits: OrganizationLimits, t: Translate, options: { requireType: boolean }) {
  return z.object({
    org_type: options.requireType
      ? z.enum(["ENTREPRISE", "BOUTIQUE", "ONG", "ORGANISATEUR_EVENEMENTS"], { errorMap: () => ({ message: t("orgNew.typeRequired") }) })
      : z.string(),
    name: z
      .string()
      .trim()
      .min(limits.name_min_length, t("orgNew.nameRequired", { min: limits.name_min_length }))
      .max(limits.name_max_length, t("orgNew.nameTooLong", { max: limits.name_max_length })),
    description: z.string().max(limits.description_max_length, t("orgNew.descriptionTooLong", { max: limits.description_max_length })),
    commune_id: z.string(),
    nif: z.string().trim().max(NIF_MAX_LENGTH, t("orgNew.nifTooLong")),
    category_ids: z
      .array(z.string())
      .max(limits.max_categories_per_context, t("categories.max", { count: limits.max_categories_per_context })),
  });
}

/** Ville de la commune choisie (le serveur exige les deux, `city_id` puis `commune_id` de la même ville). */
export function cityIdOfCommune(cities: City[], communeId: string): Uuid | null {
  if (!communeId) return null;
  return cities.find((city) => city.communes.some((commune) => commune.id === communeId))?.id ?? null;
}

export function toOrganizationInput(values: OrganizationFormValues, cities: City[]): OrganizationInput {
  const commune = values.commune_id || null;
  return {
    name: values.name.trim(),
    ...(values.org_type ? { org_type: values.org_type } : {}),
    description: values.description.trim(),
    nif: values.nif.trim(),
    category_ids: values.category_ids,
    city_id: commune ? cityIdOfCommune(cities, commune) : null,
    commune_id: commune,
  };
}

export interface BodyOptions {
  /** Nouveau logo choisi (déjà compressé). */
  logo?: File | null;
  /** Retirer le logo existant (`logo = null`). */
  removeLogo?: boolean;
}

/**
 * Corps d'une création ou d'une modification d'organisation. Multipart seulement avec un fichier de logo
 * (champs répétés pour `category_ids`, chaîne vide pour une valeur nulle) ; sinon JSON.
 * Ne contient jamais `status`, `id`, `my_role`, `created_by` ni de vendeur : le serveur les ignore ou les refuse.
 */
export function buildOrganizationBody(input: Partial<OrganizationInput>, options: BodyOptions = {}): FormData | Record<string, unknown> {
  if (options.logo) {
    const data = new FormData();
    for (const [key, value] of Object.entries(input)) {
      if (value === undefined) continue;
      if (key === "category_ids") (value as Uuid[]).forEach((id) => data.append("category_ids", id));
      else data.append(key, value === null ? "" : String(value));
    }
    data.append("logo", options.logo);
    return data;
  }
  return { ...input, ...(options.removeLogo ? { logo: null } : {}) };
}

const sameSet = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join("|") === [...b].sort().join("|");

/**
 * Champs réellement modifiés (PATCH partiel) : un nom ou un NIF renvoyé sans changement ne déclenche jamais un verrou.
 * Le NIF n'est comparé que s'il est lisible (`null` pour un éditeur ou un analyste : jamais envoyé).
 */
export function diffOrganizationInput(original: OrganizationInternal, next: OrganizationInput): Partial<OrganizationInput> {
  const changes: Partial<OrganizationInput> = {};
  if (next.name !== original.name) changes.name = next.name;
  if (next.description !== original.description) changes.description = next.description;
  if (original.nif !== null && next.nif !== original.nif) changes.nif = next.nif;
  if (!sameSet(next.category_ids, original.category_ids)) changes.category_ids = next.category_ids;
  if (next.commune_id !== original.commune_id || next.city_id !== original.city_id) {
    changes.city_id = next.city_id;
    changes.commune_id = next.commune_id;
  }
  return changes;
}

/** Une pièce validée verrouille le nom ET le NIF ; une pièce en cours d'examen verrouille déjà le nom (ADR 0006 §19.1). */
export function lockedFields(org: Pick<OrganizationInternal, "verification">): { name: "validated" | "pending" | null; nif: boolean } {
  const states = org.verification.required.map((doc) => doc.state);
  const validated = states.includes("VALIDE");
  return { name: validated ? "validated" : states.includes("EN_ATTENTE") ? "pending" : null, nif: validated };
}

/** Capacités du profil → clés i18n de la liste « Ce que vous pouvez faire » (libellés, jamais des règles : D9). */
const CAPABILITY_LABELS: [capability: string, key: string][] = [
  ["org.edit_profile", "capability.edit_profile"],
  ["org.verification_submit", "capability.verification_submit"],
  ["org.manage_members", "capability.manage_members"],
  ["org.manage_roles", "capability.manage_roles"],
  ["offer.publish", "capability.offers"],
  ["review.reply", "capability.review_reply"],
  ["contact.view_requesters", "capability.view_requesters"],
  ["contact.manage_channels", "capability.manage_channels"],
  ["message.reply", "capability.messages"],
  ["stats.view", "capability.stats"],
  ["org.archive", "capability.archive"],
];

/**
 * Clés i18n de la liste « Ce que vous pouvez faire ». Rôle Membre (`org.view_internal` et `org.leave` seulement) :
 * une ligne « Consulter l'espace… » plutôt qu'une liste vide.
 */
export function capabilityLabelKeys(capabilities: string[]): string[] {
  const keys = CAPABILITY_LABELS.filter(([capability]) => capabilities.includes(capability)).map(([, key]) => key);
  return keys.length === 0 && capabilities.includes("org.view_internal") ? ["capability.view_internal"] : keys;
}
