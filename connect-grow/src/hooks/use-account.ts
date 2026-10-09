import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient, { unwrapList } from "@/api/client";
import type { AppNotification, DashboardStats, Favorite, KycDocument, KycDocumentType, Post, User } from "@/api/types";
import { ME_QUERY_KEY, useAuth } from "@/contexts/AuthContext";
import { marketplaceKeys } from "./use-marketplace";
import { apiErrorMessage } from "./use-reviews";

export const accountKeys = {
  dashboard: ["account", "dashboard"] as const,
  trash: ["account", "trash"] as const,
  favorites: ["account", "favorites"] as const,
  notifications: ["account", "notifications"] as const,
  kyc: ["account", "kyc"] as const,
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
  const onError = (error: unknown) => toast.error(apiErrorMessage(error, "L'action n'a pas abouti. Réessayez."));

  const moveToTrash = useMutation({
    mutationFn: (id: number) => apiClient.post(`marketplace/posts/${id}/soft_delete/`),
    onSuccess: () => {
      toast.success("Annonce placée dans la corbeille.", { description: "Vous pouvez la restaurer pendant 30 jours." });
      return invalidate();
    },
    onError,
  });

  const restore = useMutation({
    mutationFn: (id: number) => apiClient.post(`marketplace/posts/${id}/restore/`),
    onSuccess: () => {
      toast.success("Annonce restaurée et de nouveau en ligne.");
      return invalidate();
    },
    onError,
  });

  const destroy = useMutation({
    mutationFn: (id: number) => apiClient.delete(`marketplace/posts/${id}/hard_delete/`),
    onSuccess: () => {
      toast.success("Annonce supprimée définitivement.");
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
    mutationFn: (id: number) => apiClient.patch(`interactions/notifications/${id}/`, { is_read: true }),
    onMutate: (id) => setAll((items) => items.map((n) => (n.id === id ? { ...n, is_read: true } : n))),
  });

  const markAllRead = useMutation({
    mutationFn: () => apiClient.post("interactions/notifications/mark_all_as_read/"),
    onMutate: () => setAll((items) => items.map((n) => ({ ...n, is_read: true }))),
    onError: () => {
      toast.error("Impossible de marquer les notifications comme lues.");
      return queryClient.invalidateQueries({ queryKey: accountKeys.notifications });
    },
  });

  return { markRead, markAllRead };
}

// --- Vérification Business (KYC, CDC 3.1) ---

export function useKycDocuments(enabled = true) {
  return useQuery({
    queryKey: accountKeys.kyc,
    queryFn: async () => unwrapList<KycDocument>((await apiClient.get("accounts/kyc/documents/")).data),
    enabled,
  });
}

export function useUploadKyc() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ type, file }: { type: KycDocumentType; file: File }) => {
      const data = new FormData();
      data.append("document_type", type);
      data.append("file", file);
      return (await apiClient.post<KycDocument>("accounts/kyc/documents/", data)).data;
    },
    onSuccess: () => {
      toast.success("Document envoyé. Il sera examiné par notre équipe.");
      return queryClient.invalidateQueries({ queryKey: accountKeys.kyc });
    },
    onError: (error) => toast.error(apiErrorMessage(error, "L'envoi du document a échoué.")),
  });
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
