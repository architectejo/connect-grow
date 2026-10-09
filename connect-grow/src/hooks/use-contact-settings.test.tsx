import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { ContactSettings } from "@/api/types";
import { contactSettingsKeys, useContactSettings, useSetContactChannel, useSetContactPhone, useVerifyContactPhone } from "./use-contact-settings";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };

const settingsFixture = (): ContactSettings => ({
  phone: { masked: "+243 81 *** ** 45", is_verified: true, login_phone_masked: "+243 81 *** ** 45", can_use_login_phone: true },
  channels: { MESSAGE: { enabled: true }, CALL: { enabled: false }, WHATSAPP: { enabled: false } },
  current_text_version: "2026-10-v1",
});

describe("hooks des réglages de contact", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lit les réglages sur accounts/contact-settings/", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: settingsFixture() });
    const { result } = renderHook(() => useContactSettings(), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.data?.channels.MESSAGE.enabled).toBe(true));
    expect(get).toHaveBeenCalledWith("accounts/contact-settings/");
  });

  it("PUT phone envoie use_login_phone ou phone et met le cache à jour", async () => {
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: settingsFixture() });
    const client = newClient();
    const { result } = renderHook(() => useSetContactPhone(), { wrapper: wrapperFor(client) });
    await act(() => result.current.mutateAsync({ use_login_phone: true }));
    await act(() => result.current.mutateAsync({ phone: "+243812345678" }));
    expect(put).toHaveBeenNthCalledWith(1, "accounts/contact-settings/phone/", { use_login_phone: true });
    expect(put).toHaveBeenNthCalledWith(2, "accounts/contact-settings/phone/", { phone: "+243812345678" });
    expect(client.getQueryData(contactSettingsKeys.all)).toEqual(settingsFixture());
  });

  it("POST verify envoie le code", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: settingsFixture() });
    const { result } = renderHook(() => useVerifyContactPhone(), { wrapper: wrapperFor(newClient()) });
    await act(() => result.current.mutateAsync("123456"));
    expect(post).toHaveBeenCalledWith("accounts/contact-settings/phone/verify/", { code: "123456" });
  });

  it("PUT canal : text_version seulement à l'activation", async () => {
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: settingsFixture() });
    const { result } = renderHook(() => useSetContactChannel(), { wrapper: wrapperFor(newClient()) });
    await act(() => result.current.mutateAsync({ channel: "CALL", enabled: true, textVersion: "2026-10-v1" }));
    await act(() => result.current.mutateAsync({ channel: "CALL", enabled: false, textVersion: "2026-10-v1" }));
    expect(put).toHaveBeenNthCalledWith(1, "accounts/contact-settings/channels/CALL/", { enabled: true, text_version: "2026-10-v1" });
    expect(put).toHaveBeenNthCalledWith(2, "accounts/contact-settings/channels/CALL/", { enabled: false });
  });
});
