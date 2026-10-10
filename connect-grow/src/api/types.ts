// Types alignés sur les serializers Django (apps/identity, marketplace, reviews, messaging,
// notifications, catalog). Tous les identifiants sont des UUID transportés en chaînes (ADR 0002).
// Les champs marqués optionnels ne sont pas toujours renvoyés par l'API : les composants
// doivent fonctionner sans eux.

/** Identifiant UUID (chaîne) de toute ressource de l'API. */
export type Uuid = string;

export type UserType = "PARTICULIER" | "ENTREPRISE";
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

export interface BusinessProfile {
    business_name: string;
    categories?: Uuid[];
    bio?: string;
    logo?: string | null;
    nif?: string;
    is_verified?: boolean;
}

/** Fiche publique d'une entreprise (PublicBusinessSerializer) : liste blanche, plus de téléphone, e-mail ni NIF. */
export interface PublicBusiness {
    id: Uuid;
    business_name: string;
    logo?: string | null;
    bio?: string;
    categories?: Uuid[];
    ville_name?: string | null;
    commune_name?: string | null;
    is_verified: boolean;
}

export interface User {
    id: Uuid;
    /** Null pour un compte inscrit par téléphone. */
    email: string | null;
    full_name: string;
    photo?: string | null;
    user_type: UserType;
    /** Null pour un compte inscrit par e-mail. */
    phone?: string | null;
    ville?: Uuid | null;
    ville_name?: string | null;
    commune?: Uuid | null;
    commune_name?: string | null;
    business_profile?: BusinessProfile | null;
    date_joined?: string;
    phone_verified?: boolean;
}

/** Vendeur tel qu'imbriqué dans une annonce (SellerSerializer). Ni téléphone ni e-mail : règle 10. */
export interface Seller {
    id: Uuid;
    full_name: string;
    photo?: string | null;
    user_type: UserType;
    business_profile?: Pick<BusinessProfile, "business_name" | "bio" | "logo" | "is_verified"> | null;
    /** Source unique de l'ancienneté (« Sur Connecte+ depuis <mois année> »). */
    date_joined?: string;
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
    /** Moyens de contact acceptés par le vendeur (ADR 0005 §5.2). Jamais de numéro. Absent des anciennes réponses. */
    allowed_channels?: ContactChannel[];
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
    seller?: string;
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
}

export type KycDocumentType = "RCCM" | "ID_NATIONALE" | "PIECE_GERANT";
export type KycStatus = "EN_ATTENTE" | "VALIDE" | "REFUSE";

export interface KycDocument {
    id: Uuid;
    document_type: KycDocumentType;
    /** URL authentifiée de téléchargement, renvoyée aux seuls examinateurs habilités (sinon null). */
    download_url?: string | null;
    status: KycStatus;
    rejection_reason?: string;
    created_at: string;
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
    /** null tant qu'aucun numéro de contact n'existe. */
    phone: ContactPhoneState | null;
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
