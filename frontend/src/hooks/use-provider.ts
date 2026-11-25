import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { ProviderInput, ProviderProfile } from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";
import { invalidateContexts } from "@/hooks/use-contexts";
import { apiErrorCode, httpStatus, shouldRetryQuery } from "@/lib/errors";

export const providerKeys = {
  all: ["provider"] as const,
};

const BASE = "accounts/provider/";

/** 404 `provider_not_found` : le profil n'est pas activé. C'est un état normal, pas une erreur. */
export const isProviderNotFound = (error: unknown) => httpStatus(error) === 404 && apiErrorCode(error) === "provider_not_found";

/** Profil prestataire du compte, ou `null` s'il n'a jamais été activé. Les autres erreurs restent des erreurs. */
export function useProvider() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: providerKeys.all,
    queryFn: async (): Promise<ProviderProfile | null> => {
      try {
        return (await apiClient.get<ProviderProfile>(BASE)).data;
      } catch (error) {
        if (isProviderNotFound(error)) return null;
        throw error;
      }
    },
    enabled: isAuthenticated,
    retry: shouldRetryQuery,
  });
}

function useAfterProviderWrite() {
  const queryClient = useQueryClient();
  return async (profile: ProviderProfile) => {
    queryClient.setQueryData(providerKeys.all, profile);
    await invalidateContexts(queryClient);
  };
}

/** Activation (201), idempotente si déjà actif (200), réactive un profil archivé (200). Gratuit : aucun plan requis. */
export function useActivateProvider() {
  const afterWrite = useAfterProviderWrite();
  return useMutation({
    mutationFn: async (input: ProviderInput) => {
      const response = await apiClient.post<ProviderProfile>(`${BASE}activate/`, input);
      return { profile: response.data, created: response.status === 201 };
    },
    onSuccess: ({ profile }) => afterWrite(profile),
  });
}

/** Modification (403 `DENY_OBJECT_STATE` si le profil est archivé). */
export function useUpdateProvider() {
  const afterWrite = useAfterProviderWrite();
  return useMutation({
    mutationFn: async (input: ProviderInput) => (await apiClient.patch<ProviderProfile>(BASE, input)).data,
    onSuccess: afterWrite,
  });
}

export function useArchiveProvider() {
  const afterWrite = useAfterProviderWrite();
  return useMutation({
    mutationFn: async () => (await apiClient.post<ProviderProfile>(`${BASE}archive/`)).data,
    onSuccess: afterWrite,
  });
}
