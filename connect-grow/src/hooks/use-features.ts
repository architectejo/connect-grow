import { useQuery } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { FeaturesResponse } from "@/api/types";
import { API_URL } from "@/config/env";

export const featuresKeys = { all: ["config", "features"] as const };

/** Le point d'entrée est hors /api/v1/ : /api/config/features/ (contrat L0-14). */
export const FEATURES_URL = `${API_URL.replace(/v\d+\/$/, "")}config/features/`;

/** Durée de fraîcheur alignée sur le Cache-Control du serveur (max-age=60). */
export const FEATURES_STALE_TIME_MS = 60_000;

/**
 * Fonctionnalités activables par le back-office. Repli sûr : tant que la configuration n'est pas lue,
 * ou si l'appel échoue, le troc est considéré comme éteint (aucune interface de troc affichée).
 */
export function useFeatures() {
  const query = useQuery({
    queryKey: featuresKeys.all,
    queryFn: async () => (await apiClient.get<FeaturesResponse>(FEATURES_URL)).data,
    staleTime: FEATURES_STALE_TIME_MS,
    retry: false,
  });
  return {
    exchangeEnabled: query.data?.features?.exchange_enabled === true,
    isLoading: query.isLoading,
  };
}
