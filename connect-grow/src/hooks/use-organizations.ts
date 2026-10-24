import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient, { unwrapList } from "@/api/client";
import type {
  OrganizationInternal,
  OrganizationKycDocument,
  OrganizationLimits,
  OrganizationVerification,
  Paginated,
  Uuid,
} from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";
import { invalidateContexts } from "@/hooks/use-contexts";
import { shouldRetryQuery } from "@/lib/errors";

// Les routes `accounts/organizations/<id>/…` désignent l'organisation par leur chemin : le profil actif n'y change
// rien (ADR 0006 §6.4). Aucune de ces réponses n'est mise en cache hors ligne (voir lib/cache-rules.ts).

export const organizationKeys = {
  all: ["organizations"] as const,
  limits: () => [...organizationKeys.all, "limits"] as const,
  internal: (id: Uuid) => [...organizationKeys.all, "internal", id] as const,
  verification: (id: Uuid) => [...organizationKeys.all, "verification", id] as const,
  documents: (id: Uuid) => [...organizationKeys.all, "documents", id] as const,
};

const BASE = "accounts/organizations/";

type Body = FormData | Record<string, unknown>;

/** Limites lues sur le serveur (plafonds de catégories et d'organisations, longueurs) : le front n'en code aucune. */
export function useOrganizationLimits() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: organizationKeys.limits(),
    queryFn: async () => (await apiClient.get<OrganizationLimits>(`${BASE}limits/`)).data,
    enabled: isAuthenticated,
    staleTime: 60 * 60 * 1000,
    retry: shouldRetryQuery,
  });
}

/** Détail interne d'une organisation (membre actif). Les refus DENY_* sont lus dans `error` par la page. */
export function useOrganization(id: Uuid | undefined) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: organizationKeys.internal(id ?? ""),
    queryFn: async () => (await apiClient.get<OrganizationInternal>(`${BASE}${id}/internal/`)).data,
    enabled: isAuthenticated && !!id,
    retry: shouldRetryQuery,
  });
}

/** Après une écriture : détail à jour dans le cache, liste des profils rechargée (nom, logo, rôle). */
function useAfterWrite(beforeRefresh?: (organization: OrganizationInternal) => void) {
  const queryClient = useQueryClient();
  return async (organization: OrganizationInternal) => {
    queryClient.setQueryData(organizationKeys.internal(organization.id), organization);
    beforeRefresh?.(organization);
    await invalidateContexts(queryClient);
  };
}

export function useCreateOrganization() {
  const afterWrite = useAfterWrite();
  return useMutation({
    mutationFn: async (body: Body) => (await apiClient.post<OrganizationInternal>(BASE, body)).data,
    onSuccess: afterWrite,
  });
}

export function useUpdateOrganization(id: Uuid) {
  const afterWrite = useAfterWrite();
  return useMutation({
    mutationFn: async (body: Body) => (await apiClient.patch<OrganizationInternal>(`${BASE}${id}/`, body)).data,
    onSuccess: afterWrite,
  });
}

/** `beforeRefresh` : appelé avant le rechargement des profils (pour quitter le profil actif avec une alerte explicite). */
export function useArchiveOrganization(id: Uuid, beforeRefresh?: () => void) {
  const afterWrite = useAfterWrite(beforeRefresh);
  return useMutation({
    mutationFn: async () => (await apiClient.post<OrganizationInternal>(`${BASE}${id}/archive/`)).data,
    onSuccess: afterWrite,
  });
}

/** Sortie volontaire (204). Retire l'organisation du cache et recharge les profils. */
export function useLeaveOrganization(id: Uuid, beforeRefresh?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.post(`${BASE}${id}/leave/`);
    },
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: organizationKeys.internal(id) });
      queryClient.removeQueries({ queryKey: organizationKeys.verification(id) });
      queryClient.removeQueries({ queryKey: organizationKeys.documents(id) });
      beforeRefresh?.();
      await invalidateContexts(queryClient);
    },
  });
}

// --- Vérification (pièces) ---

export function useOrganizationVerification(id: Uuid | undefined) {
  return useQuery({
    queryKey: organizationKeys.verification(id ?? ""),
    queryFn: async () => (await apiClient.get<OrganizationVerification>(`${BASE}${id}/verification/`)).data,
    enabled: !!id,
    retry: shouldRetryQuery,
  });
}

/** Pièces déposées (métadonnées seulement : le serveur ne renvoie jamais le fichier). */
export function useOrganizationDocuments(id: Uuid | undefined) {
  return useQuery({
    queryKey: organizationKeys.documents(id ?? ""),
    queryFn: async () => unwrapList<OrganizationKycDocument>((await apiClient.get<Paginated<OrganizationKycDocument>>(`${BASE}${id}/kyc/documents/`)).data),
    enabled: !!id,
    retry: shouldRetryQuery,
  });
}

function useInvalidateVerification(id: Uuid) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: organizationKeys.verification(id) }),
      queryClient.invalidateQueries({ queryKey: organizationKeys.documents(id) }),
      queryClient.invalidateQueries({ queryKey: organizationKeys.internal(id) }),
    ]);
}

/** Dépôt d'une pièce (multipart `document_type` + `file`). Jamais mis en file hors ligne. */
export function useUploadOrganizationDocument(id: Uuid) {
  const invalidate = useInvalidateVerification(id);
  return useMutation({
    mutationFn: async ({ type, file }: { type: string; file: File }) => {
      const data = new FormData();
      data.append("document_type", type);
      data.append("file", file);
      return (await apiClient.post<OrganizationKycDocument>(`${BASE}${id}/kyc/documents/`, data)).data;
    },
    onSuccess: invalidate,
  });
}

/** Suppression d'une pièce en attente ou refusée (409 si validée). */
export function useDeleteOrganizationDocument(id: Uuid) {
  const invalidate = useInvalidateVerification(id);
  return useMutation({
    mutationFn: async (documentId: Uuid) => {
      await apiClient.delete(`${BASE}${id}/kyc/documents/${documentId}/`);
    },
    onSuccess: invalidate,
  });
}
