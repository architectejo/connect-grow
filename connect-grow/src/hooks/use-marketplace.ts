import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import apiClient, { unwrapList } from "@/api/client";
import type {
  Category,
  City,
  OrganizationFilters,
  Paginated,
  Post,
  PostFilters,
  PublicOrganization,
  SellerContextType,
  SellerProfileData,
  Uuid,
  ViewStatPoint,
} from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";
import { loginPath } from "@/lib/auth-paths";
import { apiErrorMessage, shouldRetryQuery } from "@/lib/errors";

export const marketplaceKeys = {
  all: ["marketplace"] as const,
  categories: () => [...marketplaceKeys.all, "categories"] as const,
  cities: () => [...marketplaceKeys.all, "cities"] as const,
  postLists: () => [...marketplaceKeys.all, "posts"] as const,
  posts: (filters: PostFilters, limit?: number) => [...marketplaceKeys.postLists(), filters, limit ?? null] as const,
  post: (id: Uuid) => [...marketplaceKeys.all, "post", id] as const,
  myPosts: () => [...marketplaceKeys.all, "my-posts"] as const,
  postStats: (id: Uuid) => [...marketplaceKeys.all, "post-stats", id] as const,
  organizations: (filters: OrganizationFilters) => [...marketplaceKeys.all, "organizations", filters] as const,
  seller: (type: SellerContextType, id: Uuid) => [...marketplaceKeys.all, "seller", type, id] as const,
};

// Les référentiels changent rarement : on les garde longtemps en cache (sobriété en données)
const REFERENCE_STALE_TIME = 60 * 60 * 1000;

const cleanParams = (filters: object) =>
  Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== undefined && value !== ""));

export function useCategories() {
  return useQuery({
    queryKey: marketplaceKeys.categories(),
    queryFn: async () => unwrapList<Category>((await apiClient.get("marketplace/categories/")).data),
    staleTime: REFERENCE_STALE_TIME,
  });
}

export function useCities() {
  return useQuery({
    queryKey: marketplaceKeys.cities(),
    queryFn: async () => unwrapList<City>((await apiClient.get("marketplace/cities/")).data),
    staleTime: REFERENCE_STALE_TIME,
  });
}

export function usePosts(filters: PostFilters = {}, limit?: number, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: marketplaceKeys.posts(filters, limit),
    queryFn: async () => {
      const posts = unwrapList<Post>((await apiClient.get("marketplace/posts/", { params: cleanParams({ ...filters, near: filters.near ?? (filters.commune || undefined) }) })).data);
      return limit ? posts.slice(0, limit) : posts;
    },
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  });
}

export function usePost(id?: Uuid) {
  return useQuery({
    queryKey: marketplaceKeys.post(id ?? ""),
    queryFn: async () => (await apiClient.get<Post>(`marketplace/posts/${id}/`)).data,
    enabled: id !== undefined && id !== "",
    retry: shouldRetryQuery,
  });
}

/** Annonces actives de l'utilisateur connecté (proposition de troc). */
export function useMyPosts(enabled = true) {
  return useQuery({
    queryKey: marketplaceKeys.myPosts(),
    queryFn: async () => unwrapList<Post>((await apiClient.get("marketplace/posts/", { params: { my_posts: "true" } })).data),
    enabled,
  });
}

/** Vues des 30 derniers jours d'une annonce, pour son propriétaire. */
export function usePostStats(id: Uuid | undefined, enabled: boolean) {
  return useQuery({
    queryKey: marketplaceKeys.postStats(id ?? ""),
    queryFn: async () => ((await apiClient.get(`marketplace/stats/post/${id}/`)).data.history ?? []) as ViewStatPoint[],
    enabled: enabled && !!id,
  });
}

/**
 * Paramètres de GET accounts/organizations/ (ADR 0006 §9.2). Tous les filtres sont des filtres SERVEUR ; le tri
 * est alphabétique et ne dépend d'aucune mention de vérification, ni d'une promotion (règles 3 et 5).
 */
export function organizationsRequestParams(filters: OrganizationFilters, page: number) {
  return cleanParams({
    search: filters.search,
    org_type: filters.org_type,
    claim: filters.claim,
    fully_verified: filters.fully_verified ? "true" : undefined,
    page,
  });
}

/** Annuaire public des organisations, paginé : « Voir plus » charge la page suivante. */
export function useOrganizationDirectory(filters: OrganizationFilters) {
  return useInfiniteQuery({
    queryKey: marketplaceKeys.organizations(filters),
    queryFn: async ({ pageParam }) =>
      (await apiClient.get<Paginated<PublicOrganization>>("accounts/organizations/", { params: organizationsRequestParams(filters, pageParam) })).data,
    initialPageParam: 1,
    getNextPageParam: (last, _pages, lastPage) => (last.next ? lastPage + 1 : undefined),
    select: (data) => ({ organizations: data.pages.flatMap((page) => page.results), count: data.pages[0]?.count ?? 0 }),
    placeholderData: keepPreviousData,
    retry: shouldRetryQuery,
  });
}

/** Profil public minimal d'un vendeur (ADR 0006 §9.7). 404 : vendeur inconnu ou non public. */
export function useSellerProfile(type: SellerContextType | undefined, id: Uuid | undefined) {
  return useQuery({
    queryKey: marketplaceKeys.seller(type ?? "USER", id ?? ""),
    queryFn: async () => (await apiClient.get<SellerProfileData>(`marketplace/sellers/${type?.toLowerCase()}/${id}/`)).data,
    enabled: !!type && !!id,
    retry: shouldRetryQuery,
  });
}

// --- Favoris ---

/** Applique is_favorited à une annonce partout où elle est en cache (listes et fiche). */
function setFavoriteInCache(queryClient: QueryClient, postId: Uuid, favorited: boolean) {
  const patch = (post: Post): Post =>
    post.id === postId
      ? {
          ...post,
          is_favorited: favorited,
          favorites_count: Math.max(0, (post.favorites_count ?? 0) + (favorited ? 1 : -1)),
        }
      : post;

  queryClient.setQueriesData<Post[]>({ queryKey: marketplaceKeys.postLists() }, (posts) => posts?.map(patch));
  queryClient.setQueryData<Post>(marketplaceKeys.post(postId), (post) => (post ? patch(post) : post));
}

/**
 * Ajout/retrait d'un favori, avec mise à jour immédiate de l'interface.
 * Un visiteur non connecté est envoyé vers la connexion.
 */
export function useToggleFavorite() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();

  const mutation = useMutation({
    mutationFn: async (post: Post) =>
      (await apiClient.post<{ favorited: boolean }>(`marketplace/posts/${post.id}/favorite/`)).data,
    onMutate: (post) => {
      setFavoriteInCache(queryClient, post.id, !post.is_favorited);
    },
    onSuccess: (data, post) => {
      if (data.favorited !== !post.is_favorited) setFavoriteInCache(queryClient, post.id, data.favorited);
      toast.success(data.favorited ? "Ajoutée à vos favoris" : "Retirée de vos favoris");
    },
    onError: (error, post) => {
      setFavoriteInCache(queryClient, post.id, !!post.is_favorited);
      toast.error(apiErrorMessage(error, "Impossible de modifier vos favoris. Réessayez."));
    },
  });

  return (post: Post) => {
    if (!isAuthenticated) {
      toast.info("Connectez-vous pour enregistrer vos annonces favorites.");
      navigate(loginPath(location.pathname + location.search));
      return;
    }
    mutation.mutate(post);
  };
}
