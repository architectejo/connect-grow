import { describe, expect, it } from "vitest";
import { apiErrorCode, apiErrorMessage, retryAfterSeconds } from "@/lib/errors";
import { revealErrorInfo, revealLink } from "@/lib/contact-reveal";
import { reviewErrorMessage } from "@/lib/review-errors";
import { unwrapList } from "./client";
import fixtures from "./__fixtures__/backend-lot0.json";

/**
 * Recette du lot 0 : les réponses de `__fixtures__/backend-lot0.json` ont été enregistrées auprès du vrai
 * backend (branche `backend`, test d'intégration `apps/common/tests_recette_lot0.py`, mêmes parcours) puis
 * comparées, à l'exécution, aux types de `types.ts`. Le build (`vite build`) ne vérifie pas les types :
 * sans ce test, un écart entre `types.ts` et l'API passerait inaperçu.
 * Une clé de spécification se termine par « ? » quand `types.ts` la déclare optionnelle.
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

/** Écarts entre `data` et `spec` : clé requise absente, ou valeur d'un type non déclaré par types.ts. */
function mismatches(data: Record<string, unknown>, spec: Record<string, string>): string[] {
  const problems: string[] = [];
  for (const [rawKey, kinds] of Object.entries(spec)) {
    const key = rawKey.replace(/\?$/, "");
    if (!(key in data)) {
      if (!rawKey.endsWith("?")) problems.push(`clé requise absente : ${key}`);
      continue;
    }
    if (!kinds.split("|").some((kind) => KINDS[kind](data[key]))) {
      problems.push(`${key} = ${JSON.stringify(data[key])} (attendu ${kinds})`);
    }
  }
  return problems;
}

const RATING = { average: "num|null", count: "num" };
const SELLER = { id: "uuid", full_name: "str", "photo?": "str|null", user_type: "str", "business_profile?": "obj|null", "date_joined?": "date" };
const POST = {
  id: "uuid", seller: "obj", "seller_name?": "str", category: "uuid", "category_name?": "str|null", commune: "uuid",
  "commune_name?": "str|null", post_type: "str", title: "str", description: "str", price: "str", "currency?": "str",
  "condition?": "str|null", "stock?": "num", "is_price_negotiable?": "bool", "is_exchangeable?": "bool",
  "main_image?": "str|null", "images?": "list", "is_favorited?": "bool", "favorites_count?": "num", views_count: "num",
  likes_count: "num", created_at: "date", "status?": "str", "expires_at?": "date|null", "visibility_score?": "num",
  "visibility_rank?": "str", "is_trending?": "bool", "is_sponsored?": "bool", offer_rating: "obj", seller_rating: "obj",
  "shares_count?": "num", allowed_channels: "list",
};
const REVIEW = {
  id: "uuid", post: "uuid|null", is_mine: "bool", user_name: "str", offer_rating: "num", seller_rating: "num", content: "str",
  source: "str", "reply_content?": "str|null", "reply_at?": "date|null", created_at: "date", "edited_at?": "date|null",
  "is_post_owner?": "bool", "can_edit?": "bool", "can_delete?": "bool", "contest_report_id?": "uuid|null", "contest_responded?": "bool",
};
const ELIGIBILITY = { can_review: "bool", reason: "str|null", available_at: "date|null", review_id: "uuid|null" };
const NOTIFICATION = { id: "uuid", "user?": "uuid", notification_type: "str", title: "str", content: "str", "link?": "str|null", is_read: "bool", created_at: "date" };
const KYC = {
  id: "uuid", document_type: "str", "download_url?": "str|null", status: "str", "rejection_reason?": "str", created_at: "date",
  "reviewed_at?": "date|null",
};
const BUSINESS = {
  id: "uuid", business_name: "str", "logo?": "str|null", "bio?": "str", "categories?": "list", "ville_name?": "str|null",
  "commune_name?": "str|null", is_verified: "bool",
};
const USER = {
  id: "uuid", email: "str|null", full_name: "str", "photo?": "str|null", user_type: "str", "phone?": "str|null", "ville?": "uuid|null",
  "ville_name?": "str|null", "commune?": "uuid|null", "commune_name?": "str|null", "business_profile?": "obj|null", "date_joined?": "date",
  "phone_verified?": "bool",
};
const PAGE = { count: "num", next: "str|null", previous: "str|null", results: "list" };
const DASHBOARD_SUMMARY = {
  total_views: "num", today_views: "num", active_posts: "num", avg_rating: "num|null", review_count: "num",
  "contacts_count?": "num", "contact_rate?": "num",
};

type Row = Record<string, unknown>;
const f = fixtures as unknown as Record<string, Row & Row[]>;

describe("contrat backend -> types.ts (réponses réelles du lot 0)", () => {
  it("Post : détail et liste, notes toujours présentes, vendeur sans coordonnées", () => {
    const detail = f.post_detail as Row;
    expect(mismatches(detail, POST)).toEqual([]);
    expect(mismatches(detail.seller as Row, SELLER)).toEqual([]);
    expect(mismatches(detail.offer_rating as Row, RATING)).toEqual([]);
    expect(mismatches(detail.seller_rating as Row, RATING)).toEqual([]);
    const list = unwrapList<Row>(f.post_list);
    expect(list.length).toBeGreaterThan(0);
    expect(mismatches(list[0], POST)).toEqual([]);
    for (const key of ["phone", "email", "nif"]) expect(detail.seller).not.toHaveProperty(key);
    expect(detail.is_sponsored).toBe(false);
  });

  it("Review : avis de l'auteur, avis public avec réponse, avis contesté", () => {
    for (const name of ["review_mine", "review_replied_public", "review_contested_author"]) {
      expect(mismatches(f[name] as Row, REVIEW), name).toEqual([]);
    }
    const contested = f.review_contested_author as Row;
    expect(contested.is_mine).toBe(true);
    expect(contested.contest_report_id).toMatch(UUID);
    expect(contested.contest_responded).toBe(false);
    const pub = f.review_replied_public as Row;
    expect(pub.is_mine).toBe(false);
    expect(pub.contest_report_id).toBeNull();
    for (const key of ["user", "user_id", "contact_channel", "contact_event_id"]) expect(pub).not.toHaveProperty(key);
  });

  it("ReviewEligibility : cas autorisé et cas « trop tôt » avec available_at", () => {
    expect(mismatches(f.eligibility_ok as Row, ELIGIBILITY)).toEqual([]);
    expect(f.eligibility_ok).toMatchObject({ can_review: true, reason: null });
    expect(mismatches(f.eligibility_too_early as Row, ELIGIBILITY)).toEqual([]);
    expect(f.eligibility_too_early).toMatchObject({ can_review: false, reason: "too_early" });
    expect(f.eligibility_too_early.available_at).toMatch(DATE);
  });

  it("Notification, KycDocument, Favorite, DashboardStats, entreprises paginées", () => {
    for (const notification of unwrapList<Row>(f.notifications)) expect(mismatches(notification, NOTIFICATION)).toEqual([]);
    expect(mismatches(f.kyc as Row, KYC)).toEqual([]);
    expect(f.kyc.download_url).toBeNull();
    expect(f.kyc).not.toHaveProperty("file");
    expect(f.favorite).toEqual({ favorited: true });
    const favorites = unwrapList<Row>(f.favorites);
    expect(mismatches(favorites[0], { id: "uuid", post: "obj", created_at: "date" })).toEqual([]);
    expect(mismatches(f.dashboard.summary as unknown as Row, DASHBOARD_SUMMARY)).toEqual([]);
    expect(mismatches(f.businesses as unknown as Row, PAGE)).toEqual([]);
    const business = (f.businesses.results as unknown as Row[])[0];
    expect(mismatches(business, BUSINESS)).toEqual([]);
    for (const key of ["phone", "email", "nif", "full_name", "date_joined"]) expect(business).not.toHaveProperty(key);
  });

  it("User : e-mail, téléphone et noms de localisation pouvant être null (R0-02)", () => {
    expect(mismatches(f.me_business as Row, USER)).toEqual([]);
    expect(mismatches(f.me_phone_only as Row, USER)).toEqual([]);
    expect(f.me_phone_only).toMatchObject({ email: null, ville_name: null, commune_name: null });
  });

  it("ConversationItem : last_message présent, post et participant sans coordonnées", () => {
    const conversation = unwrapList<Row>(f.conversations)[0];
    expect(conversation.post).toMatch(UUID);
    expect(conversation.other_participant).not.toHaveProperty("phone");
    expect(conversation.other_participant).not.toHaveProperty("email");
    expect(typeof (conversation.last_message as Row).content).toBe("string");
  });
});

describe("contact vendeur : réponses réelles (ADR 0005 §5.2, 5.4, 5.5)", () => {
  const FAKE_PHONE = /^\+243\d{9}$/;

  it("allowed_channels : liste de canaux connus sur le détail et la liste, sans numéro", () => {
    const known = ["MESSAGE", "CALL", "WHATSAPP"];
    for (const post of [f.post_detail as Row, ...unwrapList<Row>(f.post_list)]) {
      expect(post.allowed_channels).toBeInstanceOf(Array);
      for (const channel of post.allowed_channels as string[]) expect(known).toContain(channel);
      expect(JSON.stringify(post)).not.toMatch(/\+243\d{9}|tel:|wa\.me/);
    }
  });

  it("reveal CALL et WHATSAPP : clés exactes, liens cohérents avec le canal, 201", () => {
    const keys = ["contact_event_id", "channel", "created", "phone", "tel_url", "whatsapp_url"];
    const call = f.reveal_call as unknown as { status: number; body: Row };
    const wa = f.reveal_whatsapp as unknown as { status: number; body: Row };
    expect(call.status).toBe(201);
    expect(Object.keys(call.body).sort()).toEqual([...keys].sort());
    expect(mismatches(call.body, { contact_event_id: "uuid", channel: "str", created: "bool", phone: "str", tel_url: "str|null", whatsapp_url: "str|null" })).toEqual([]);
    expect(call.body.phone).toMatch(FAKE_PHONE);
    expect(call.body).toMatchObject({ channel: "CALL", whatsapp_url: null });
    expect(call.body.tel_url).toBe(`tel:${call.body.phone}`);
    expect(wa.body).toMatchObject({ channel: "WHATSAPP", tel_url: null });
    expect(revealLink("CALL", call.body as never)).toBe(call.body.tel_url);
    expect(revealLink("WHATSAPP", wa.body as never)).toBe(wa.body.whatsapp_url);
  });

  it("reveals/received : page DRF, nom abrégé et offre, ni numéro ni identifiant du visiteur", () => {
    for (const page of [f.reveals_received, f.reveals_received_call]) {
      expect(mismatches(page as unknown as Row, PAGE)).toEqual([]);
      const rows = (page as unknown as { results: Row[] }).results;
      expect(rows.length).toBeGreaterThan(0);
      for (const row of rows) {
        expect(mismatches(row, { id: "uuid", channel: "str", created_at: "date", requester_display_name: "str", offer: "obj" })).toEqual([]);
        expect(mismatches(row.offer as Row, { id: "uuid", title: "str" })).toEqual([]);
        expect(Object.keys(row).sort()).toEqual(["channel", "created_at", "id", "offer", "requester_display_name"]);
        expect(JSON.stringify(row)).not.toMatch(/\+243\d{9}|tel:|wa\.me/);
      }
    }
    const filtered = (f.reveals_received_call as unknown as { results: Row[] }).results;
    expect(filtered.every((row) => row.channel === "CALL")).toBe(true);
  });

  it("channel_invalid : 400 avec code, classé sans nouvelle tentative", () => {
    const { status, body } = f.reveal_error_channel_invalid as unknown as { status: number; body: unknown };
    const error = { response: { status, data: body } };
    expect(apiErrorCode(error)).toBe("channel_invalid");
    expect(revealErrorInfo(error).kind).toBe("blocked");
  });
});

describe("erreurs réelles du backend vs helpers du front", () => {
  const axiosError = (status: number, data: unknown, headers: Record<string, string> = {}) => ({ response: { status, data, headers } });

  it("429 : Retry-After en secondes et code `throttled` exploités", () => {
    const { status, retry_after, body } = f.throttled as unknown as { status: number; retry_after: string; body: unknown };
    const error = axiosError(status, body, { "retry-after": retry_after });
    expect(retryAfterSeconds(error)).toBe(Number(retry_after));
    expect(apiErrorCode(error)).toBe("throttled");
    expect(apiErrorMessage(error)).toMatch(/\d/);
  });

  it("429 : sans l'en-tête (CORS), le délai est lu dans le corps réel", () => {
    const { status, retry_after, body } = f.throttled as unknown as { status: number; retry_after: string; body: unknown };
    expect(retryAfterSeconds(axiosError(status, body))).toBe(Number(retry_after));
  });

  it("401 de connexion : code no_active_account, message métier du front", () => {
    const error = axiosError(401, f.login_401);
    expect(apiErrorCode(error)).toBe("no_active_account");
  });

  it("refus d'avis sans contact : code not_eligible traduit par le front", () => {
    const error = axiosError(403, f.review_error);
    expect(apiErrorCode(error)).toBe("not_eligible");
    expect(reviewErrorMessage(error)).toBe("Vous pourrez donner votre avis après avoir contacté le vendeur.");
  });
});
