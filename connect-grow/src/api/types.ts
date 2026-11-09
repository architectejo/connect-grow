// Types alignés sur les serializers Django (apps/identity, marketplace, reviews, messaging,
// notifications, catalog). Tous les identifiants sont des UUID transportés en chaînes (ADR 0002).
// Les champs marqués optionnels ne sont pas toujours renvoyés par l'API : les composants
// doivent fonctionner sans eux.

/** Identifiant UUID (chaîne) de toute ressource de l'API. */
export type Uuid = string;

export type Currency = "USD" | "CDF";
export type PostType = "PRODUIT" | "SERVICE";
export type PostCondition = "NEUF" | "OCCASION" | "RECONDITIONNE";
export type VisibilityRank = "Elite" | "Standard" | "Faible";
export type PostStatus = "ACTIVE" | "PAUSED" | "SOLD" | "EXPIRED";
export type PostBadge = "sponsored" | "trending";

/**
 * Moyenne arithmétique arrondie à 1 décimale ; `average` vaut null sous le seuil d'affichage
 * (réglage du back-office), `count` reste exact (avis masqués exclus).
 */
export interface RatingSummary {
    average: number | null;
    count: number;
}

export interface User {
    id: Uuid;
    /** Null pour un compte inscrit par téléphone. */
    email: string | null;
    full_name: string;
    photo?: string | null;
    /** Null pour un compte inscrit par e-mail. */
    phone?: string | null;
    ville?: Uuid | null;
    ville_name?: string | null;
    commune?: Uuid | null;
    commune_name?: string | null;
    date_joined?: string;
    /** Le numéro de connexion a été vérifié par SMS (lecture seule ; ADR 0006 §17.1). */
    phone_verified?: boolean;
}

/** Mention de vérification précise (« RCCM vérifié ») ; le libellé du serveur ne sert que de repli (ADR 0006 §9.2). */
export interface VerifiedClaim {
    code: ClaimCode | string;
    label: string;
    verified_at: string | null;
}

export type ClaimCode = "RCCM_VERIFIED" | "NATIONAL_ID_VERIFIED" | "REPRESENTATIVE_VERIFIED" | "NGO_DECREE_VERIFIED";

/** « Organisation vérifiée » n'existe que si toutes les pièces exigées sont validées, et se lit avec la liste des mentions. */
export interface VerificationSummary {
    complete: boolean;
    label: string | null;
}

export type SellerContextType = "USER" | "PROVIDER" | "ORGANIZATION";

/**
 * Vendeur d'une offre (ADR 0006 §9.6) : le profil sous lequel l'offre est publiée. Ni téléphone, ni e-mail, ni
 * identifiant de compte (règle 10). Ne jamais le renvoyer dans un POST/PATCH d'offre (400 `seller_not_settable`).
 */
export interface Seller {
    context_type: SellerContextType;
    context_id: Uuid;
    display_name: string;
    photo?: string | null;
    org_type?: OrganizationType | null;
    verified_claims: VerifiedClaim[];
    verification_summary: VerificationSummary;
    /** Source unique de l'ancienneté (« Sur Connecte+ depuis <mois année> »). */
    member_since?: string | null;
}

export interface PostImage {
    id: Uuid;
    image: string;
    order?: number;
}

export interface Post {
    id: Uuid;
    seller: Seller;
    seller_name?: string;
    category: Uuid;
    category_name?: string;
    commune: Uuid;
    commune_name?: string;
    post_type: PostType;
    title: string;
    description: string;
    price: string;
    currency?: Currency;
    condition?: PostCondition | null;
    stock?: number;
    is_price_negotiable?: boolean;
    /** Absent des réponses tant que le troc est éteint côté serveur (L0-14). */
    is_exchangeable?: boolean;
    main_image?: string | null;
    /** Photos supplémentaires de la galerie (main_image non comprise). */
    images?: PostImage[];
    is_favorited?: boolean;
    favorites_count?: number;
    views_count: number;
    likes_count: number;
    created_at: string;
    /** Cycle de vie de l'offre (remplace is_active, absent de l'API). */
    status?: PostStatus;
    expires_at?: string | null;
    visibility_score?: number;
    visibility_rank?: VisibilityRank;
    /** Badges fournis par le module ranking (prioritaires sur is_trending / is_sponsored). */
    badges?: PostBadge[];
    is_trending?: boolean;
    is_sponsored?: boolean;
    /** Note de l'offre (ADR 0004 §7.1). Absente des anciennes réponses : les composants s'en passent. */
    offer_rating?: RatingSummary;
    /** Note du contexte vendeur de l'offre ; jamais fusionnée avec la note de l'offre. */
    seller_rating?: RatingSummary;
    shares_count?: number;
    /** Réservé au vendeur : l'offre est masquée par la modération. */
    is_hidden_by_moderation?: boolean;
    /** Moyens de contact acceptés par le vendeur (ADR 0005 §5.2). Jamais de numéro. */
    allowed_channels: ContactChannel[];
    /** Le demandeur peut modifier cette offre (membre avec `offer.edit`, ou titulaire) ; ADR 0006 §9.6. */
    is_owner?: boolean;
}

export interface Category {
    id: Uuid;
    name: string;
    icon?: string;
    slug: string;
}

export interface Commune {
    id: Uuid;
    name: string;
    city: Uuid;
}

export interface City {
    id: Uuid;
    name: string;
    communes: Commune[];
}

export interface Paginated<T> {
    count: number;
    next: string | null;
    previous: string | null;
    results: T[];
}

export interface PostFilters {
    search?: string;
    category?: string;
    city?: string;
    commune?: string;
    currency?: Currency | "";
    condition?: PostCondition | "";
    is_exchangeable?: "true" | "";
    price_min?: string;
    price_max?: string;
    ordering?: PostOrdering | "";
    /** Identifiant du contexte vendeur (et non d'un compte), avec `seller_type` pour lever l'ambiguïté. */
    seller?: string;
    seller_type?: SellerContextType;
    /** Commune de référence pour la proximité (D) du classement ; un identifiant invalide est ignoré par l'API. */
    near?: string;
}

export type PostOrdering = "-visibility_score" | "-created_at" | "price" | "-price";

/** Avis (ADR 0004 §7.2). La seule source est le contact : libellé « Avis après contact ». */
export interface Review {
    id: Uuid;
    /** Offre concernée ; null si elle a été purgée. */
    post: Uuid | null;
    /** Vrai si l'avis est celui du visiteur connecté (l'identifiant de l'auteur n'est jamais public). */
    is_mine: boolean;
    /** Nom public de l'auteur (prénom + initiale), tel que renvoyé par l'API. */
    user_name: string;
    offer_rating: number;
    seller_rating: number;
    content: string;
    source: "CONTACT";
    reply_content?: string | null;
    reply_at?: string | null;
    created_at: string;
    /** Renseigné quand l'auteur a modifié son avis. */
    edited_at?: string | null;
    is_post_owner?: boolean;
    /** Vrai tant que l'auteur peut modifier ou supprimer son avis (fenêtre ouverte, ni masqué, ni signalé, sans réponse du vendeur). */
    can_edit?: boolean;
    /** Vrai tant que l'auteur peut supprimer son avis (mêmes conditions que can_edit). */
    can_delete?: boolean;
    /** Identifiant du signalement « contact fictif » ouvert qui conteste cet avis. Réservé à l'auteur ; null sinon. */
    contest_report_id?: Uuid | null;
    /** Vrai si l'auteur a déjà répondu au signalement (une seule réponse). Réservé à l'auteur. */
    contest_responded?: boolean;
}

export type ReviewEligibilityReason =
    | "own_offer"
    | "no_contact"
    | "too_early"
    | "account_too_new"
    | "contact_rejected"
    | "already_reviewed"
    | "recently_deleted"
    | "offer_unavailable";

/** Réponse de GET /interactions/reviews/eligibility/?post= : seul le serveur décide du droit d'avis. */
export interface ReviewEligibility {
    can_review: boolean;
    reason: ReviewEligibilityReason | null;
    /** Date à partir de laquelle l'avis sera possible (reason = too_early ou account_too_new). */
    available_at: string | null;
    /** Avis déjà donné (reason = already_reviewed). */
    review_id: Uuid | null;
}

/** Réponse de POST /moderation/reports/{id}/author-response/. */
export interface AuthorResponseResult {
    id: Uuid;
    status: string;
    author_responded_at: string;
}

export interface ReviewInput {
    offer_rating: number;
    seller_rating: number;
    content: string;
}

export interface ViewStatPoint {
    day: string;
    views: number;
}

export interface DashboardSummary {
    total_views: number;
    today_views: number;
    active_posts: number;
    /** Moyenne des notes vendeur visibles (1 décimale) ; null sans avis, sans seuil d'affichage (privé au vendeur). */
    avg_rating: number | null;
    review_count: number;
    contacts_count?: number;
    contact_rate?: number;
}

export interface DashboardStats {
    history: ViewStatPoint[];
    summary: DashboardSummary;
}

export interface Favorite {
    id: Uuid;
    post: Post;
    created_at: string;
}

export type NotificationType = "COMMENT" | "CONTACT" | "EXCHANGE" | "MESSAGE" | "SYSTEM";

export interface AppNotification {
    id: Uuid;
    /** Destinataire (identifiant de l'utilisateur connecté). */
    user?: Uuid;
    notification_type: NotificationType;
    title: string;
    content: string;
    link?: string | null;
    is_read: boolean;
    created_at: string;
    /** Profil auquel la notification est rattachée (organisation, prestataire) ; null pour le profil personnel (ADR 0006 §9.8). */
    context?: { type: ContextType; id: Uuid; name: string } | null;
}

export type KycDocumentType = "RCCM" | "ID_NATIONALE" | "PIECE_GERANT" | "ARRETE_ONG";
export type KycStatus = "EN_ATTENTE" | "VALIDE" | "REFUSE";

/**
 * Pièce de vérification d'une organisation (ADR 0006 §9.4). Le serveur ne renvoie jamais l'URL ni le contenu du
 * fichier : seuls les examinateurs habilités le téléchargent.
 */
export interface OrganizationKycDocument {
    id: Uuid;
    document_type: KycDocumentType;
    document_type_label: string;
    status: KycStatus;
    rejection_reason?: string;
    uploaded_at: string;
    reviewed_at?: string | null;
}

// --- Contact du vendeur et consentement par canal (ADR 0005 §5.1) ---

export type ContactChannel = "MESSAGE" | "CALL" | "WHATSAPP";

export interface ContactPhoneState {
    /** Toujours masqué par le serveur (jamais le numéro complet). */
    masked: string;
    is_verified: boolean;
    login_phone_masked: string;
    can_use_login_phone: boolean;
}

export interface ContactChannelState {
    enabled: boolean;
    granted_at?: string | null;
    text_version?: string;
}

export interface ContactSettings {
    /** Profil auquel s'appliquent ces réglages (ADR 0006 §9.8, §17.1). */
    context: { type: ContextType; id: Uuid };
    /**
     * Canaux que ce profil a le droit de configurer (ADR 0006 §17.1, Q-F3) : une organisation n'a que `MESSAGE`
     * tant que l'appel et WhatsApp lui sont fermés. Différent de `allowed_channels` d'une offre (canal effectif).
     */
    available_channels: ContactChannel[];
    /** null tant qu'aucun numéro de contact n'existe. */
    phone: ContactPhoneState | null;
    /** Masque du numéro de connexion ; null sans numéro, et toujours null pour une organisation (`login_phone_not_allowed`). */
    login_phone_masked: string | null;
    /** Numéro de connexion présent et vérifié, donc utilisable comme numéro de contact (jamais vrai pour une organisation). */
    can_use_login_phone: boolean;
    channels: Record<ContactChannel, ContactChannelState>;
    current_text_version: string;
}

export type ContactPhoneInput = { use_login_phone: true } | { phone: string };

/** Canaux qui révèlent un numéro (le message passe par POST interactions/contacts/). */
export type RevealChannel = "CALL" | "WHATSAPP";

/**
 * Réponse de POST interactions/contacts/reveal/ (ADR 0005 §5.4). Contient le numéro du vendeur :
 * à garder en état local uniquement, jamais en cache persistant, stockage ni journal.
 */
export interface RevealedContact {
    contact_event_id: Uuid;
    channel: RevealChannel;
    created: boolean;
    phone: string;
    tel_url: string | null;
    whatsapp_url: string | null;
}

/** Ligne de « Qui a demandé » (ADR 0005 §5.5) : nom abrégé et offre, jamais d'identifiant du visiteur ni de numéro. */
export interface ReceivedReveal {
    id: Uuid;
    channel: RevealChannel;
    created_at: string;
    requester_display_name: string;
    offer: { id: Uuid; title: string };
}

/** GET /api/v1/config/features/ (sous /api/v1/) : fonctionnalités activables par le back-office. */
export interface FeaturesResponse {
  features: { exchange_enabled: boolean };
}

// --- Contextes (profils) du compte : GET accounts/contexts/ (ADR 0006 §9.1) ---

export type ContextType = "USER" | "PROVIDER" | "ORGANIZATION";
export type OrganizationRole = "OWNER" | "ADMIN" | "EDITOR" | "ANALYST";
export type OrganizationType = "ENTREPRISE" | "BOUTIQUE" | "ONG" | "ORGANISATEUR_EVENEMENTS";

/** Élément de `contexts/` : un profil sous lequel le compte peut agir. `capabilities` ne sert qu'à masquer des boutons. */
export interface AvailableContext {
  type: ContextType;
  id: Uuid;
  name: string;
  /** Rôle dans l'organisation ; null pour le profil personnel et le prestataire. */
  role: OrganizationRole | null;
  org_type: OrganizationType | null;
  /** Prestataire : photo du compte (pas de champ propre). */
  photo: string | null;
  capabilities: string[];
  /** Organisation issue d'un ancien compte entreprise. */
  migrated_from_business: boolean;
  /** `ACTIVE` dans `results`. Absent (serveur plus ancien) : traité comme `ACTIVE`. */
  status: OrganizationStatus;
}

/**
 * Organisation `SUSPENDED` ou `ARCHIVED` dont le compte est membre actif (L0-09 UX-SUSP, section 3).
 * Jamais de motif, de date, d'auteur de décision, de NIF ni de liste de membres (règle 10).
 */
export interface UnavailableOrganization extends Omit<AvailableContext, "type" | "status" | "role" | "org_type"> {
  type: "ORGANIZATION";
  status: "SUSPENDED" | "ARCHIVED";
  role: OrganizationRole;
  org_type: OrganizationType;
}

export interface ContextsResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: AvailableContext[];
  /** Absent = `[]` (serveur plus ancien). */
  unavailable?: UnavailableOrganization[];
}

/** Réponse de `contexts/` normalisée par le front : `unavailable` toujours présent, `status` toujours renseigné. */
export interface ContextsData {
  results: AvailableContext[];
  unavailable: UnavailableOrganization[];
}

// --- Organisations (ADR 0006 §9.2, §17.2, §19.1) ---

export type OrganizationStatus = "ACTIVE" | "SUSPENDED" | "ARCHIVED";

/** État d'une pièce exigée dans `OrganizationInternal.verification.required`. */
export type RequiredDocumentState = "NONE" | "EN_ATTENTE" | "VALIDE" | "REFUSE";

export interface RequiredDocument {
    document_type: KycDocumentType;
    label: string;
    state: RequiredDocumentState;
}

export interface OrganizationVerificationBlock {
    required: RequiredDocument[];
    verified_claims: VerifiedClaim[];
    summary: VerificationSummary;
}

/** Détail réservé aux membres actifs. `nif` n'est renseigné que pour le propriétaire et les administrateurs (règle 10). */
export interface OrganizationInternal {
    id: Uuid;
    name: string;
    org_type: OrganizationType;
    description: string;
    logo: string | null;
    nif: string | null;
    city_id: Uuid | null;
    commune_id: Uuid | null;
    category_ids: Uuid[];
    status: OrganizationStatus;
    created_at: string;
    my_role: OrganizationRole;
    capabilities: string[];
    /** Organisation issue d'un ancien compte entreprise. Absent : faux (la clé disparaîtra avec la migration). */
    migrated_from_business?: boolean;
    verification: OrganizationVerificationBlock;
}

/** Élément de la liste publique `organizations/` : liste blanche stricte, ni NIF, ni statut, ni coordonnées, ni membres. */
export interface PublicOrganization {
    id: Uuid;
    name: string;
    org_type: OrganizationType;
    description: string;
    logo: string | null;
    city_id: Uuid | null;
    commune_id: Uuid | null;
    category_ids: Uuid[];
    verified_claims: VerifiedClaim[];
    verification_summary: VerificationSummary;
    member_since: string;
}

export interface OrganizationFilters {
    search?: string;
    org_type?: OrganizationType | "";
    claim?: ClaimCode | "";
    fully_verified?: boolean;
}

/** `organizations/limits/` : limites lues dans les réglages du serveur (le front ne code aucune limite). */
export interface OrganizationLimits {
    max_categories_per_context: number;
    max_organizations_per_account: number;
    name_min_length: number;
    name_max_length: number;
    description_max_length: number;
}

/** Corps de création/modification : jamais `status`, `id`, `my_role`, ni `org_type` en modification. */
export interface OrganizationInput {
    name: string;
    org_type?: OrganizationType;
    description: string;
    nif: string;
    category_ids: Uuid[];
    city_id: Uuid | null;
    commune_id: Uuid | null;
}

/** État de vérification renvoyé par `organizations/<id>/verification/` (ADR 0006 §9.4 ; état `MANQUANTE` si rien n'est déposé). */
export type RequirementStatus = KycStatus | "MANQUANTE";

export interface VerificationRequirement {
    document_type: KycDocumentType;
    document_type_label: string;
    claim_code: ClaimCode | string;
    claim_label: string;
    status: RequirementStatus;
    rejection_reason: string;
}

export interface OrganizationVerification {
    verified_claims: VerifiedClaim[];
    summary: VerificationSummary;
    requirements: VerificationRequirement[];
}

// --- Prestataire individuel (ADR 0006 §9.3) ---

export type ProviderStatus = "ACTIVE" | "ARCHIVED";

export interface ProviderProfile {
    id: Uuid;
    display_name: string;
    bio: string;
    category_ids: Uuid[];
    status: ProviderStatus;
    created_at: string;
}

export interface ProviderInput {
    display_name?: string;
    bio?: string;
    category_ids?: Uuid[];
}

// --- Profil public d'un vendeur (ADR 0006 §9.7) ---

/** `marketplace/sellers/<user|provider|organization>/<uuid>/` : aucun téléphone, e-mail, adresse exacte ni membre. */
export interface SellerProfileData {
    context_type: SellerContextType;
    context_id: Uuid;
    display_name: string;
    photo: string | null;
    /** Description de l'organisation, bio du prestataire, null pour un compte personnel. */
    description: string | null;
    org_type: OrganizationType | null;
    verified_claims: VerifiedClaim[];
    verification_summary: VerificationSummary;
    member_since: string | null;
    seller_rating: RatingSummary;
    active_offers_count: number;
}
