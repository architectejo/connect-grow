import { useMutation } from "@tanstack/react-query";
import apiClient from "@/api/client";

export type OtpPurpose = "REGISTER" | "LOGIN" | "PASSWORD_RESET";

/** Envoi d'un code par SMS (CDC 3.1). La réponse est toujours un 200 au message uniforme (le serveur ne révèle pas si le numéro est éligible) ; les demandes sont limitées (429). */
export function useRequestOtp() {
  return useMutation({
    mutationFn: async ({ phone, purpose }: { phone: string; purpose: OtpPurpose }) =>
      (await apiClient.post<{ message: string; expires_in_minutes: number }>("accounts/otp/request/", { phone, purpose })).data,
  });
}
