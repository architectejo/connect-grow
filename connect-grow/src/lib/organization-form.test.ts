import { describe, expect, it } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { City, OrganizationInput, OrganizationInternal } from "@/api/types";
import {
  buildOrganizationBody,
  capabilityLabelKeys,
  cityIdOfCommune,
  diffOrganizationInput,
  FALLBACK_LIMITS,
  lockedFields,
  organizationSchema,
  toOrganizationInput,
} from "./organization-form";

const t = (key: string, options?: Record<string, unknown>) => i18n.t(key, options) as string;
const CITY = "11111111-1111-4111-8111-111111111111";
const COMMUNE = "22222222-2222-4222-8222-222222222222";
const CAT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const CAT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const cities: City[] = [{ id: CITY, name: "Kinshasa", communes: [{ id: COMMUNE, name: "Gombe", city: CITY }] }];

const org = (over: Partial<OrganizationInternal> = {}): OrganizationInternal => ({
  id: "o1",
  name: "Atelier X",
  org_type: "ENTREPRISE",
  description: "Couture",
  logo: null,
  nif: "A1",
  city_id: CITY,
  commune_id: COMMUNE,
  category_ids: [CAT_A],
  status: "ACTIVE",
  created_at: "2026-10-10T10:00:00+01:00",
  my_role: "OWNER",
  capabilities: [],
  verification: { required: [{ document_type: "RCCM", label: "RCCM", state: "NONE" }], verified_claims: [], summary: { complete: false, label: null } },
  ...over,
});

const input = (over: Partial<OrganizationInput> = {}): OrganizationInput => ({
  name: "Atelier X",
  description: "Couture",
  nif: "A1",
  category_ids: [CAT_A],
  city_id: CITY,
  commune_id: COMMUNE,
  ...over,
});

describe("buildOrganizationBody", () => {
  it("JSON sans logo ; retirer le logo envoie logo = null", () => {
    expect(buildOrganizationBody({ name: "X" })).toEqual({ name: "X" });
    expect(buildOrganizationBody({ name: "X" }, { removeLogo: true })).toEqual({ name: "X", logo: null });
  });

  it("multipart avec un logo : category_ids répétés, valeur nulle en chaîne vide", () => {
    const file = new File(["x"], "logo.webp", { type: "image/webp" });
    const body = buildOrganizationBody(input({ category_ids: [CAT_A, CAT_B], commune_id: null, city_id: null }), { logo: file }) as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.getAll("category_ids")).toEqual([CAT_A, CAT_B]);
    expect(body.get("commune_id")).toBe("");
    expect(body.get("logo")).toBeInstanceOf(File);
  });

  it("n'envoie jamais de vendeur, de statut, de rôle ni de créateur", () => {
    const file = new File(["x"], "logo.webp");
    const keys = [...(buildOrganizationBody(input(), { logo: file }) as FormData).keys()];
    for (const key of keys) expect(key).not.toMatch(/^(seller|created_by|status|id|my_role)/);
    expect(Object.keys(buildOrganizationBody(input()) as object).join()).not.toMatch(/seller|created_by|status|my_role/);
  });
});

describe("diffOrganizationInput", () => {
  it("rien n'est envoyé quand rien n'a changé (un nom ou un NIF inchangé ne déclenche aucun verrou)", () => {
    expect(diffOrganizationInput(org(), input())).toEqual({});
  });

  it("seuls les champs modifiés sont envoyés ; ville et commune vont ensemble", () => {
    const changes = diffOrganizationInput(org(), input({ description: "Nouvelle", commune_id: null, city_id: null, category_ids: [CAT_B] }));
    expect(changes).toEqual({ description: "Nouvelle", category_ids: [CAT_B], city_id: null, commune_id: null });
  });

  it("l'ordre des catégories ne compte pas", () => {
    expect(diffOrganizationInput(org({ category_ids: [CAT_A, CAT_B] }), input({ category_ids: [CAT_B, CAT_A] }))).toEqual({});
  });

  it("le NIF illisible (null pour un éditeur ou un analyste) n'est jamais envoyé", () => {
    expect(diffOrganizationInput(org({ nif: null }), input({ nif: "Z9" }))).toEqual({});
  });
});

describe("lockedFields", () => {
  const state = (...states: string[]) =>
    org({
      verification: {
        required: states.map((s, i) => ({ document_type: ["RCCM", "ID_NATIONALE", "PIECE_GERANT"][i] as "RCCM", label: "x", state: s as "NONE" })),
        verified_claims: [],
        summary: { complete: false, label: null },
      },
    });
  it("rien de verrouillé sans pièce, ou avec une pièce refusée", () => {
    expect(lockedFields(state("NONE", "NONE"))).toEqual({ name: null, nif: false });
    expect(lockedFields(state("REFUSE"))).toEqual({ name: null, nif: false });
  });
  it("en cours d'examen : nom verrouillé seulement", () => {
    expect(lockedFields(state("EN_ATTENTE", "NONE"))).toEqual({ name: "pending", nif: false });
  });
  it("validée : nom et NIF verrouillés (validée prime sur en cours)", () => {
    expect(lockedFields(state("EN_ATTENTE", "VALIDE"))).toEqual({ name: "validated", nif: true });
  });
});

describe("organizationSchema", () => {
  const schema = organizationSchema(FALLBACK_LIMITS, t, { requireType: true });
  const valid = { org_type: "BOUTIQUE", name: "Boutique Gombe", description: "", commune_id: "", nif: "", category_ids: [] };

  it("accepte un formulaire minimal (catégories, commune et NIF facultatifs)", () => {
    expect(schema.safeParse(valid).success).toBe(true);
  });

  it("refuse un type absent, un nom trop court ou trop long, trop de catégories, un NIF trop long", () => {
    expect(schema.safeParse({ ...valid, org_type: "" }).success).toBe(false);
    expect(schema.safeParse({ ...valid, name: " A " }).success).toBe(false);
    expect(schema.safeParse({ ...valid, name: "A".repeat(FALLBACK_LIMITS.name_max_length + 1) }).success).toBe(false);
    expect(schema.safeParse({ ...valid, category_ids: ["1", "2", "3", "4", "5", "6"] }).success).toBe(false);
    expect(schema.safeParse({ ...valid, nif: "9".repeat(51) }).success).toBe(false);
  });

  it("les plafonds viennent des limites du serveur, pas du code", () => {
    const strict = organizationSchema({ ...FALLBACK_LIMITS, max_categories_per_context: 1, description_max_length: 10 }, t, { requireType: false });
    expect(strict.safeParse({ ...valid, category_ids: ["1", "2"] }).success).toBe(false);
    expect(strict.safeParse({ ...valid, description: "x".repeat(11) }).success).toBe(false);
    expect(strict.safeParse({ ...valid, org_type: "" }).success).toBe(true);
  });
});

describe("ville et commune", () => {
  it("la ville est déduite de la commune choisie", () => {
    expect(cityIdOfCommune(cities, COMMUNE)).toBe(CITY);
    expect(cityIdOfCommune(cities, "")).toBeNull();
    expect(cityIdOfCommune(cities, "inconnue")).toBeNull();
  });
  it("toOrganizationInput nettoie les espaces et lie ville et commune", () => {
    const result = toOrganizationInput(
      { org_type: "ONG", name: "  Aide Kin ", description: " Texte ", commune_id: COMMUNE, nif: " 12 ", category_ids: [CAT_A] },
      cities,
    );
    expect(result).toEqual({ name: "Aide Kin", org_type: "ONG", description: "Texte", nif: "12", category_ids: [CAT_A], city_id: CITY, commune_id: COMMUNE });
  });
});

describe("capabilityLabelKeys", () => {
  it("dérive les libellés des capacités du serveur, sans règle de rôle codée en dur", () => {
    expect(capabilityLabelKeys(["stats.view", "offer.view_internal"])).toEqual(["capability.stats"]);
    expect(capabilityLabelKeys(["offer.publish", "org.edit_profile"])).toEqual(["capability.edit_profile", "capability.offers"]);
    expect(capabilityLabelKeys([])).toEqual([]);
  });
});
