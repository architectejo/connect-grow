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
export type PostBadge = "sponsored" | "trending" | "reliable";

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
    email: string;
    full_name: string;
    photo?: string | null;
    user_type: UserType;
    phone?: string;
    ville?: Uuid | null;
    ville_name?: string;
    commune?: Uuid | null;
    commune_name?: string;
    business_profile?: BusinessProfile | null;
    date_joined?: string;
    phone_verified?: boolean;
    trust_score?: number | null;
    reviews_count?: number;
}

/** Vendeur tel qu'imbriqué dans une annonce (SellerSerializer). */
export interface Seller {
    id: Uuid;
    full_name: string;
    photo?: string | null;
    phone?: string;
    user_type: UserType;
    business_profile?: Pick<BusinessProfile, "business_name" | "bio" | "logo" | "is_verified"> | null;
    date_joined?: string;
    /** Ancienne moyenne brute, remplacée par trust_score. */
    avg_rating?: number;
    reviews_count?: number;
    /** Trust Score bayésien (CDC 3.7) ; null tant que le vendeur a moins de 3 avis. */
    trust_score?: number | null;
    is_new_seller?: boolean;
    /** Badge « Vendeur fiable » : Trust Score ≥ 4,5 et au moins 10 avis. */
    is_trusted_seller?: boolean;
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
    comments_count?: number;
    shares_count?: number;
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
}

export type PostOrdering = "-visibility_score" | "-created_at" | "price" | "-price";

export interface Review {
    id: Uuid;
    /** Offre concernée ; null si elle a été purgée. */
    post: Uuid | null;
    deal?: Uuid;
    user_id: Uuid;
    reviewed_user_id?: Uuid;
    user_name: string;
    content: string;
    rating: number;
    reply_content?: string | null;
    reply_at?: string | null;
    created_at: string;
    is_post_owner?: boolean;
    /** Vrai tant que l'auteur peut modifier son avis (48 h, ni masqué ni signalé). */
    can_edit?: boolean;
}

export interface ViewStatPoint {
    day: string;
    views: number;
}

export interface DashboardSummary {
    total_views: number;
    today_views: number;
    active_posts: number;
    avg_rating: number;
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
