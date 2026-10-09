// Types alignés sur les serializers Django (apps/accounts, apps/marketplace).
// Les champs marqués « prévu » viennent du cahier des charges et ne sont pas encore
// renvoyés par l'API : les composants doivent fonctionner sans eux.

export type UserType = "PARTICULIER" | "ENTREPRISE";
export type Currency = "USD" | "CDF";
export type PostType = "PRODUIT" | "SERVICE";
export type PostCondition = "NEUF" | "OCCASION" | "RECONDITIONNE";
export type VisibilityRank = "Elite" | "Standard" | "Faible";
export type PostBadge = "sponsored" | "trending" | "reliable";

export interface BusinessProfile {
    business_name: string;
    categories?: number[];
    bio?: string;
    logo?: string | null;
    nif?: string;
    is_verified?: boolean;
}

export interface User {
    id: number;
    email: string;
    full_name: string;
    photo?: string | null;
    user_type: UserType;
    phone?: string;
    ville?: number | null;
    ville_name?: string;
    commune?: number | null;
    commune_name?: string;
    business_profile?: BusinessProfile | null;
    date_joined?: string;
    phone_verified?: boolean;
    trust_score?: number | null;
    reviews_count?: number;
}

/** Vendeur tel qu'imbriqué dans une annonce (SellerSerializer). */
export interface Seller {
    id: number;
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
    id: number;
    image: string;
    order?: number;
}

export interface Post {
    id: number;
    seller: Seller;
    seller_name?: string;
    category: number;
    category_name?: string;
    commune: number;
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
    is_active?: boolean;
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
    id: number;
    name: string;
    icon?: string;
    slug: string;
}

export interface Commune {
    id: number;
    name: string;
    city: number;
}

export interface City {
    id: number;
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
    id: number;
    post: number;
    user_id: number;
    user_name: string;
    content: string;
    rating: number;
    reply_content?: string | null;
    reply_at?: string | null;
    created_at: string;
    is_post_owner?: boolean;
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
}

export interface DashboardStats {
    history: ViewStatPoint[];
    summary: DashboardSummary;
}

export interface Favorite {
    id: number;
    post: Post;
    created_at: string;
}

export type NotificationType = "COMMENT" | "CONTACT" | "EXCHANGE" | "MESSAGE" | "SYSTEM";

export interface AppNotification {
    id: number;
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
    id: number;
    document_type: KycDocumentType;
    file?: string;
    status: KycStatus;
    rejection_reason?: string;
    created_at: string;
    reviewed_at?: string | null;
}
