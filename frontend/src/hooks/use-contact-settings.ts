import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { ContactChannel, ContactPhoneInput, ContactSettings } from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";

export const contactSettingsKeys = {
  all: ["account", "contact-settings"] as const,
};

const BASE = "accounts/contact-settings/";

/** Réglages de contact du vendeur (numéro masqué, consentements). Toutes les écritures renvoient le même corps que le GET. */
export function useContactSettings(enabled = true) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: contactSettingsKeys.all,
    queryFn: async () => (await apiClient.get<ContactSettings>(BASE)).data,
    enabled: isAuthenticated && enabled,
  });
}

function useSettingsMutation<TInput>(request: (input: TInput) => Promise<{ data: ContactSettings }>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: TInput) => (await request(input)).data,
    onSuccess: (settings) => queryClient.setQueryData(contactSettingsKeys.all, settings),
  });
}

export const useSetContactPhone = () =>
  useSettingsMutation((input: ContactPhoneInput) => apiClient.put<ContactSettings>(`${BASE}phone/`, input));

export const useVerifyContactPhone = () =>
  useSettingsMutation((code: string) => apiClient.post<ContactSettings>(`${BASE}phone/verify/`, { code }));

/** `textVersion` est obligatoire pour activer CALL ou WHATSAPP : c'est la version du texte que la personne a lu. */
export const useSetContactChannel = () =>
  useSettingsMutation(({ channel, enabled, textVersion }: { channel: ContactChannel; enabled: boolean; textVersion?: string }) =>
    apiClient.put<ContactSettings>(`${BASE}channels/${channel}/`, {
      enabled,
      ...(enabled && textVersion ? { text_version: textVersion } : {}),
    }),
  );
