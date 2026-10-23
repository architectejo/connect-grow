import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { AvailableContext, OrganizationInternal, OrganizationKycDocument, OrganizationLimits, Post } from "@/api/types";
import { describeApiError, organizationDeniedKey } from "@/lib/api-errors";
import { availableChannels } from "@/lib/contact-settings";
import { latestByType } from "@/lib/kyc-files";
import { capabilityLabelKeys, lockedFields, organizationSchema } from "@/lib/organization-form";
import { offerAccess, sellerPathOf } from "@/lib/post";
import { isProviderNotFound } from "@/hooks/use-provider";
import identity from "./__fixtures__/backend-identity.json";

/**
 * Recette F2 (L0-09) : les réponses de `__fixtures__/backend-identity.json` ont été enregistrées auprès du backend
 * d'intégration integ/L0-09 (script jetable hors dépôt, base de test en mémoire, données fictives) puis comparées
 * aux types de `types.ts` et aux assistants du front. Une clé se termine par « ? » quand `types.ts` la déclare optionnelle.
 */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const DATE = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$/;
const KINDS: Record<string, (value: unknown) => boolean> = {
  null: (v) => v === null,
  str: (v) => typeof v === "string",
  uuid: (v) => typeof v === "string" && UUID.test(v),
  date: (v) => typeof v === "string" && DATE.test(v),
  num: (v) => typeof v === "number",
  bool: (v) => typeof v === "boolean",
  list: (v) => Array.isArray(v),
  obj: (v) => typeof v === "object" && v !== null && !Array.isArray(v),
};

type Row = Record<string, unknown>;
const f = identity as unknown as Record<string, Row & { status?: number; body?: Row }>;

function mismatches(data: Row, spec: Record<string, string>): string[] {
  const problems: string[] = [];
  for (const [rawKey, kinds] of Object.entries(spec)) {
    const key = rawKey.replace(/\?$/, "");
    if (!(key in data)) {
      if (!rawKey.endsWith("?")) problems.push(`clé requise absente : ${key}`);
      continue;
    }
    if (!kinds.split("|").some((kind) => KINDS[kind](data[key]))) problems.push(`${key} = ${JSON.stringify(data[key])} (attendu ${kinds})`);
  }
  return problems;
}

/** Erreur axios minimale construite à partir d'une réponse enregistrée. */
const errorOf = (name: string) => ({ response: { status: f[name].status, data: f[name].body, headers: {} } });
const t = (key: string, options?: Record<string, unknown>) => i18n.t(key, options) as string;

const CONTEXT = {
  type: "str", id: "uuid", name: "str", role: "str|null", org_type: "str|null", photo: "str|null", capabilities: "list", migrated_from_business: "bool",
};
const ORGANIZATION = {
  id: "uuid", name: "str", org_type: "str", description: "str", logo: "str|null", nif: "str|null", city_id: "uuid|null", commune_id: "uuid|null",
  category_ids: "list", status: "str", created_at: "date", my_role: "str", capabilities: "list", "migrated_from_business?": "bool", verification: "obj",
};
const PUBLIC_ORGANIZATION = {
  id: "uuid", name: "str", org_type: "str", description: "str", logo: "str|null", city_id: "uuid|null", commune_id: "uuid|null",
  category_ids: "list", verified_claims: "list", verification_summary: "obj", member_since: "date",
};
const PAGE = { count: "num", next: "str|null", previous: "str|null", results: "list" };

describe("contextes (GET accounts/contexts/)", () => {
  const results = (f.contexts as unknown as { results: Row[] }).results;

  it("ordre USER, PROVIDER, ORGANIZATION et clés exactes de chaque profil", () => {
    expect(mismatches(f.contexts as Row, PAGE)).toEqual([]);
    expect(results.map((row) => row.type)).toEqual(["USER", "PROVIDER", "ORGANIZATION"]);
    for (const row of results) {
      expect(mismatches(row, CONTEXT)).toEqual([]);
      expect(Object.keys(row).sort()).toEqual(Object.keys(CONTEXT).sort());
    }
  });

  it("les capacités `org.*` n'existent que pour une organisation (le personnel et le prestataire n'ont que des capacités de contenu)", () => {
    for (const row of results) {
      const caps = row.capabilities as string[];
      expect(caps.some((cap) => cap.startsWith("org."))).toBe(row.type === "ORGANIZATION");
    }
  });

  it("le profil actif retire le profil perdu : un départ d'organisation laisse la liste sans elle", () => {
    const after = (f.contexts_after_leave as unknown as { results: Row[] }).results;
    expect(after.map((row) => row.type)).toEqual(["USER"]);
  });
});

describe("OrganizationInternal", () => {
  const owner = f.organization_internal_owner as unknown as OrganizationInternal;
  const analyst = f.organization_internal_analyst as unknown as OrganizationInternal;

  it("respecte types.ts, avec les rôles et capacités fournis par le serveur", () => {
    expect(mismatches(owner as unknown as Row, ORGANIZATION)).toEqual([]);
    expect(owner.my_role).toBe("OWNER");
    expect(owner.capabilities).toContain("org.archive");
    expect(analyst.my_role).toBe("ANALYST");
    expect(analyst.capabilities).toEqual(expect.arrayContaining(["org.leave", "org.view_internal"]));
    expect(analyst.capabilities).not.toContain("org.edit_profile");
  });

  it("minimisation (règle 10) : le NIF n'est lu que par le propriétaire et les administrateurs ; jamais de membres ni de coordonnées", () => {
    expect(typeof owner.nif).toBe("string");
    expect(analyst.nif).toBeNull();
    for (const org of [owner, analyst]) {
      for (const key of ["members", "phone", "email", "created_by", "owner", "is_verified"]) expect(org).not.toHaveProperty(key);
    }
  });

  it("les libellés de capacités de l'écran suivent les capacités du serveur", () => {
    expect(capabilityLabelKeys(owner.capabilities)).toContain("capability.archive");
    expect(capabilityLabelKeys(analyst.capabilities)).toEqual(["capability.stats"]);
  });

  it("verrous du nom et du NIF (ADR 0006 §19.1) : en attente verrouille le nom, validée verrouille aussi le NIF", () => {
    expect(lockedFields(owner)).toEqual({ name: null, nif: false });
    expect(lockedFields(f.organization_internal_pending as unknown as OrganizationInternal)).toEqual({ name: "pending", nif: false });
    expect(lockedFields(f.organization_internal_validated as unknown as OrganizationInternal)).toEqual({ name: "validated", nif: true });
  });

  it("un refus de renommer est un 409 `name_locked_by_verification`, traduit par le front", () => {
    for (const name of ["organization_name_locked_error", "organization_name_locked_pending_error"]) {
      expect(f[name].status).toBe(409);
      expect(describeApiError(errorOf(name))).toBe(t("errors.code.name_locked_by_verification"));
    }
    expect(f.organization_nif_locked_error.status).toBe(409);
    expect(describeApiError(errorOf("organization_nif_locked_error"))).toBe(t("errors.code.nif_locked_by_verification"));
  });
});

describe("liste publique des organisations", () => {
  const page = f.organizations_list as unknown as { count: number; results: Row[] };

  it("clés exactes (test d'exhaustivité du serveur) : ni NIF, ni statut, ni coordonnées, ni membres", () => {
    expect(mismatches(page as unknown as Row, PAGE)).toEqual([]);
    expect(page.results.length).toBeGreaterThan(0);
    for (const row of page.results) {
      expect(mismatches(row, PUBLIC_ORGANIZATION)).toEqual([]);
      expect(Object.keys(row).sort()).toEqual(Object.keys(PUBLIC_ORGANIZATION).sort());
    }
  });

  it("une mention est un code précis traduit par le front, jamais « Vérifié » seul", () => {
    const claim = (page.results[0].verified_claims as Row[])[0];
    expect(claim.code).toBe("RCCM_VERIFIED");
    expect(t(`claims.${claim.code as string}`)).toBe("RCCM vérifié");
    expect(JSON.stringify(page)).not.toMatch(/is_verified/);
  });
});

describe("vérification des pièces", () => {
  const verification = f.verification_mixed as unknown as { requirements: Row[]; verified_claims: Row[]; summary: Row };
  const documents = (f.kyc_documents as unknown as { results: OrganizationKycDocument[] }).results;

  it("états MANQUANTE / EN_ATTENTE / VALIDE / REFUSE avec motif du refus", () => {
    expect(verification.requirements.map((item) => item.status)).toEqual(["VALIDE", "REFUSE", "MANQUANTE"]);
    expect(verification.requirements[1].rejection_reason).toBe("Document illisible");
    expect(verification.summary).toEqual({ complete: false, label: null });
  });

  it("chaque pièce exigée a un titre et une consigne en français (clés kyc.docs.*)", () => {
    for (const item of verification.requirements) {
      expect(t(`kyc.docs.${item.document_type as string}.title`)).not.toMatch(/^kyc\.docs/);
      expect(t(`kyc.docs.${item.document_type as string}.description`)).not.toMatch(/^kyc\.docs/);
      expect(t(`claims.${item.claim_code as string}`)).not.toMatch(/^claims\./);
    }
  });

  it("une pièce déposée ne contient jamais l'URL ni le contenu du fichier", () => {
    for (const doc of documents) {
      expect(Object.keys(doc).sort()).toEqual(
        ["document_type", "document_type_label", "id", "rejection_reason", "reviewed_at", "status", "uploaded_at"].sort(),
      );
    }
    expect(JSON.stringify(f.kyc_document_created)).not.toMatch(/file|url|private_media/i);
  });

  it("la pièce la plus récente de chaque type est retenue", () => {
    expect([...latestByType(documents).keys()].sort()).toEqual(["ID_NATIONALE", "RCCM"]);
  });

  it("erreurs d'envoi : type non exigé (400, champ), format refusé (400, champ), non autorisé (403 DENY_PERMISSION), pièce validée (409)", () => {
    expect(f.kyc_error_not_required.status).toBe(400);
    expect(f.kyc_error_not_required.body).toHaveProperty("document_type");
    expect(f.kyc_error_bad_file.body).toHaveProperty("file");
    expect(describeApiError(errorOf("kyc_error_permission"), { inOrganization: true })).toBe(t("errors.deny.PERMISSION.org"));
    expect(f.kyc_delete_validated_error.status).toBe(409);
  });
});

describe("prestataire", () => {
  it("profil actif, désactivé puis réactivé ; non activé = 404 provider_not_found, un état normal", () => {
    const provider = f.provider as unknown as Row;
    expect(mismatches(provider, { id: "uuid", display_name: "str", bio: "str", category_ids: "list", status: "str", created_at: "date" })).toEqual([]);
    expect(provider.status).toBe("ACTIVE");
    expect((f.provider_archived as unknown as Row).status).toBe("ARCHIVED");
    expect((f.provider_reactivated as unknown as Row).status).toBe("ACTIVE");
    expect(isProviderNotFound(errorOf("provider_not_found_error"))).toBe(true);
  });

  it("modifier un profil désactivé : 403 DENY_OBJECT_STATE", () => {
    expect(f.provider_patch_archived_error.status).toBe(403);
    expect((f.provider_patch_archived_error.body as Row).code).toBe("DENY_OBJECT_STATE");
  });
});

describe("limites et codes d'erreur de l'écran de création", () => {
  const limits = f.limits as unknown as OrganizationLimits;

  it("limits/ : le front ne code aucune limite, le schéma suit les valeurs du serveur", () => {
    expect(mismatches(limits as unknown as Row, { max_categories_per_context: "num", max_organizations_per_account: "num", name_min_length: "num", name_max_length: "num", description_max_length: "num" })).toEqual([]);
    const schema = organizationSchema(limits, t, { requireType: true });
    const valid = { org_type: "ONG", name: "Aide Kin", description: "", commune_id: "", nif: "", category_ids: [] };
    expect(schema.safeParse(valid).success).toBe(true);
    expect(schema.safeParse({ ...valid, name: "A" }).success).toBe(false);
    expect(schema.safeParse({ ...valid, category_ids: Array.from({ length: limits.max_categories_per_context + 1 }, (_, i) => String(i)) }).success).toBe(false);
  });

  it("phone_verification_required (403), organization_limit_reached (409), last_owner (409) : textes français dédiés", () => {
    expect(describeApiError(errorOf("organization_create_phone_error"))).toBe(t("errors.code.phone_verification_required"));
    expect(describeApiError(errorOf("organization_limit_error"))).toBe(t("errors.code.organization_limit_reached"));
    expect(describeApiError(errorOf("organization_last_owner_error"))).toBe(t("errors.code.last_owner"));
    expect(describeApiError(errorOf("organization_last_owner_error"), { demote: true })).toBe(t("errors.code.last_owner_demote"));
  });

  it("nom trop court : erreur de champ DRF, sans code", () => {
    expect(f.organization_create_bad_name_error.status).toBe(400);
    expect(f.organization_create_bad_name_error.body).toHaveProperty("name");
  });

  it("refus d'accès à l'espace d'une organisation : non-membre, archivée", () => {
    expect(organizationDeniedKey(errorOf("organization_internal_outsider_error"))).toBe("org.denied.relation");
    expect(organizationDeniedKey(errorOf("organization_internal_archived_error"))).toBe("org.denied.archived");
    expect((f.organization_internal_archived_error.body as Row).code).toBe("DENY_OBJECT_STATE");
  });
});

describe("objet seller des offres (ADR 0006 §9.6)", () => {
  const posts = {
    USER: f.post_detail_user as unknown as Post,
    PROVIDER: f.post_detail_provider as unknown as Post,
    ORGANIZATION: f.post_detail_organization as unknown as Post,
  };
  const contexts = (f.contexts as unknown as { results: AvailableContext[] }).results;

  it("une offre par type de vendeur : clés exactes, type toujours présent", () => {
    for (const [type, post] of Object.entries(posts)) {
      expect(Object.keys(post.seller).sort()).toEqual(
        ["context_id", "context_type", "display_name", "member_since", "org_type", "photo", "verification_summary", "verified_claims"].sort(),
      );
      expect(post.seller.context_type).toBe(type);
      expect(sellerPathOf(post.seller)).toBe(`/seller/${type.toLowerCase()}/${post.seller.context_id}`);
    }
    expect(posts.ORGANIZATION.seller.org_type).toBe("ENTREPRISE");
    expect(posts.USER.seller.org_type).toBeNull();
  });

  it("compte personnel : nom abrégé (« Nom O. »), jamais le nom complet", () => {
    expect(posts.USER.seller.display_name).toMatch(/^\S+ \p{Lu}\.$/u);
    expect(JSON.stringify(f.post_detail_user)).not.toMatch(/owner@example\.com/);
  });

  it("organisation sans canal de contact : allowed_channels vide (pas de bouton, message explicite côté interface)", () => {
    expect(posts.ORGANIZATION.allowed_channels).toEqual([]);
    expect(posts.USER.allowed_channels).toEqual(["MESSAGE"]);
  });

  it("la mention de vérification de l'organisation est un code précis, sans « vérifié » seul", () => {
    expect(posts.ORGANIZATION.seller.verified_claims.map((claim) => claim.code)).toEqual(["RCCM_VERIFIED"]);
    expect(posts.ORGANIZATION.seller.verification_summary).toEqual({ complete: false, label: null });
  });

  it("droits sur l'offre déduits des profils du compte (is_owner n'est pas renvoyé par l'API d'intégration)", () => {
    expect(posts.ORGANIZATION).not.toHaveProperty("is_owner");
    expect(offerAccess(posts.ORGANIZATION, contexts)).toEqual({ canEdit: true, isMember: true });
    expect(offerAccess(posts.USER, contexts)).toEqual({ canEdit: true, isMember: true });
    expect(offerAccess(posts.ORGANIZATION, contexts.filter((c) => c.type === "USER"))).toEqual({ canEdit: false, isMember: false });
    const analyst = [{ type: "ORGANIZATION" as const, id: posts.ORGANIZATION.seller.context_id, capabilities: ["offer.view_internal", "stats.view"] }];
    expect(offerAccess(posts.ORGANIZATION, analyst)).toEqual({ canEdit: false, isMember: true });
  });

  it("publier : un analyste reçoit 403 DENY_PERMISSION ; un vendeur dans le corps est refusé (400, champ seller_context_id)", () => {
    expect(describeApiError(errorOf("post_publish_analyst_error"), { inOrganization: true })).toBe(t("errors.deny.PERMISSION.org"));
    expect(f.post_seller_not_settable_error.status).toBe(400);
    expect(f.post_seller_not_settable_error.body).toHaveProperty("seller_context_id");
  });

  it("le formulaire d'offre n'envoie jamais de vendeur : ni seller, ni seller_*, ni created_by", () => {
    const source = readFileSync(resolve(process.cwd(), "src/pages/PostEditor.tsx"), "utf-8");
    expect(source).not.toMatch(/append\(\s*["'`](seller|created_by)/);
    expect(source).not.toMatch(/seller_context|seller_is_public/);
  });
});

describe("compte et réglages de contact", () => {
  it("me/ expose phone_verified (booléen), sans type de compte ni profil entreprise", () => {
    expect((f.me_owner as unknown as Row).phone_verified).toBe(true);
    expect((f.me_unverified as unknown as Row).phone_verified).toBe(false);
    for (const name of ["me_owner", "me_unverified"]) {
      expect(f[name]).not.toHaveProperty("user_type");
      expect(f[name]).not.toHaveProperty("business_profile");
    }
  });

  it("canaux proposables : le client suit available_channels du serveur ; clé absente, repli prudent (organisation = message seul)", () => {
    expect(availableChannels(f.contact_settings_organization as never, "ORGANIZATION")).toEqual(["MESSAGE"]);
    expect(availableChannels(f.contact_settings_user as never, "USER")).toEqual(["MESSAGE", "CALL", "WHATSAPP"]);
    expect(availableChannels({ available_channels: ["MESSAGE", "CALL"] }, "ORGANIZATION")).toEqual(["MESSAGE", "CALL"]);
  });
});
