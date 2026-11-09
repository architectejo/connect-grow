import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import i18n from "@/i18n";
import apiClient, { unwrapList } from "@/api/client";
import type { AppNotification, DashboardStats, Favorite, Post, Uuid, User } from "@/api/types";
import { ME_QUERY_KEY, useAuth } from "@/contexts/AuthContext";
import { marketplaceKeys } from "./use-marketplace";
import { apiErrorMessage } from "@/lib/errors";

export const accountKeys = {
  dashboard: ["account", "dashboard"] as const,
  trash: ["account", "trash"] as const,
  favorites: ["account", "favorites"] as const,
  notifications: ["account", "notifications"] as const,
};

// --- Tableau de bord ---

export function useDashboardStats() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: accountKeys.dashboard,
    queryFn: async () => (await apiClient.get<DashboardStats>("marketplace/stats/dashboard/")).data,
    enabled: isAuthenticated,
  });
}

// --- Cycle de vie des annonces (corbeille, CDC 3.10) ---

/** Après une action sur une annonce, toutes les listes concernées sont rechargées. */
function useInvalidatePosts() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: marketplaceKeys.all }),
      queryClient.invalidateQueries({ queryKey: accountKeys.trash }),
      queryClient.invalidateQueries({ queryKey: accountKeys.dashboard }),
    ]);
}

export function useTrash() {
  return useQuery({
    queryKey: accountKeys.trash,
    queryFn: async () => unwrapList<Post>((await apiClient.get("marketplace/posts/trash/")).data),
  });
}

export function usePostLifecycle() {
  const invalidate = useInvalidatePosts();
  const onError = (error: unknown) => toast.error(apiErrorMessage(error, i18n.t("feedback.actionFailed")));

  const moveToTrash = useMutation({
    mutationFn: (id: Uuid) => apiClient.post(`marketplace/posts/${id}/soft_delete/`),
    onSuccess: () => {
      toast.success(i18n.t("feedback.movedToTrash"), { description: i18n.t("feedback.movedToTrashHint") });
      return invalidate();
    },
    onError,
  });

  const restore = useMutation({
    mutationFn: (id: Uuid) => apiClient.post(`marketplace/posts/${id}/restore/`),
    onSuccess: () => {
      toast.success(i18n.t("feedback.restored"));
      return invalidate();
    },
    onError,
  });

  const destroy = useMutation({
    mutationFn: (id: Uuid) => apiClient.delete(`marketplace/posts/${id}/hard_delete/`),
    onSuccess: () => {
      toast.success(i18n.t("feedback.deleted"));
      return invalidate();
    },
    onError,
  });

  return { moveToTrash, restore, destroy };
}

// --- Favoris ---

export function useFavorites() {
  return useQuery({
    queryKey: accountKeys.favorites,
    queryFn: async () => unwrapList<Favorite>((await apiClient.get("marketplace/favorites/")).data),
  });
}

// --- Notifications (CDC 3.6) ---

export function useNotifications(options: { poll?: boolean } = {}) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: accountKeys.notifications,
    queryFn: async () => unwrapList<AppNotification>((await apiClient.get("interactions/notifications/")).data),
    enabled: isAuthenticated,
    // P1 : pas encore de temps réel, on interroge le serveur toutes les 30 s (pas en arrière-plan)
    refetchInterval: options.poll ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
}

export function useNotificationActions() {
  const queryClient = useQueryClient();
  const setAll = (fn: (items: AppNotification[]) => AppNotification[]) =>
    queryClient.setQueryData<AppNotification[]>(accountKeys.notifications, (items) => (items ? fn(items) : items));

  const markRead = useMutation({
    mutationFn: (id: Uuid) => apiClient.patch(`interactions/notifications/${id}/`, { is_read: true }),
    onMutate: (id) => setAll((items) => items.map((n) => (n.id === id ? { ...n, is_read: true } : n))),
  });

  const markAllRead = useMutation({
    mutationFn: () => apiClient.post("interactions/notifications/mark_all_as_read/"),
    onMutate: () => setAll((items) => items.map((n) => ({ ...n, is_read: true }))),
    onError: () => {
      toast.error(i18n.t("feedback.markReadFailed"));
      return queryClient.invalidateQueries({ queryKey: accountKeys.notifications });
    },
  });

  return { markRead, markAllRead };
}

// --- Profil ---

/** Mise à jour du profil (multipart pour la photo et le logo) ; rafraîchit l'utilisateur courant. */
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: FormData | Record<string, unknown>) => (await apiClient.patch<User>("accounts/me/", data)).data,
    onSuccess: (user) => {
      queryClient.setQueryData(ME_QUERY_KEY, user);
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (input: { old_password: string; new_password: string }) => apiClient.post("accounts/change-password/", input),
  });
}
