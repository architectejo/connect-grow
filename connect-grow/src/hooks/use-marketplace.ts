import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import apiClient, { unwrapList } from "@/api/client";
import type { Category, City, Post, PostFilters, User, ViewStatPoint } from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";
import { loginPath } from "@/lib/auth-paths";

export const marketplaceKeys = {
  all: ["marketplace"] as const,
  categories: () => [...marketplaceKeys.all, "categories"] as const,
  cities: () => [...marketplaceKeys.all, "cities"] as const,
  postLists: () => [...marketplaceKeys.all, "posts"] as const,
  posts: (filters: PostFilters, limit?: number) => [...marketplaceKeys.postLists(), filters, limit ?? null] as const,
  post: (id: string | number) => [...marketplaceKeys.all, "post", String(id)] as const,
  myPosts: () => [...marketplaceKeys.all, "my-posts"] as const,
  postStats: (id: string | number) => [...marketplaceKeys.all, "post-stats", String(id)] as const,
  businesses: (search: string) => [...marketplaceKeys.all, "businesses", search] as const,
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
      const posts = unwrapList<Post>((await apiClient.get("marketplace/posts/", { params: cleanParams(filters) })).data);
      return limit ? posts.slice(0, limit) : posts;
    },
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  });
}

export function usePost(id?: string | number) {
  return useQuery({
    queryKey: marketplaceKeys.post(id ?? ""),
    queryFn: async () => (await apiClient.get<Post>(`marketplace/posts/${id}/`)).data,
    enabled: id !== undefined && id !== "",
    retry: (count, error: { response?: { status?: number } }) => error?.response?.status !== 404 && count < 1,
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
export function usePostStats(id: string | number | undefined, enabled: boolean) {
  return useQuery({
    queryKey: marketplaceKeys.postStats(id ?? ""),
    queryFn: async () => ((await apiClient.get(`marketplace/stats/post/${id}/`)).data.history ?? []) as ViewStatPoint[],
    enabled: enabled && !!id,
  });
}

export function useBusinesses(search: string) {
  return useQuery({
    queryKey: marketplaceKeys.businesses(search),
    queryFn: async () =>
      unwrapList<User>((await apiClient.get("accounts/businesses/", { params: cleanParams({ search }) })).data),
    placeholderData: keepPreviousData,
  });
}

// --- Favoris ---

/** Applique is_favorited à une annonce partout où elle est en cache (listes et fiche). */
function setFavoriteInCache(queryClient: QueryClient, postId: number, favorited: boolean) {
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
    onError: (_error, post) => {
      setFavoriteInCache(queryClient, post.id, !!post.is_favorited);
      toast.error("Impossible de modifier vos favoris. Réessayez.");
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
