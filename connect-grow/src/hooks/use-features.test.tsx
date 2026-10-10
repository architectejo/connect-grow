import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import apiClient from "@/api/client";
import { FEATURES_STALE_TIME_MS, FEATURES_URL, useFeatures } from "./use-features";

// Le client de test garde le comportement par défaut de React Query (3 nouvelles tentatives),
// afin de prouver que useFeatures désactive lui-même les nouvelles tentatives.
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

describe("useFeatures", () => {
  afterEach(() => vi.restoreAllMocks());

  it("appelle /api/config/features/ (hors /api/v1/) et expose le troc allumé", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: { features: { exchange_enabled: true } } });
    const { result } = renderHook(() => useFeatures(), { wrapper });
    await waitFor(() => expect(result.current.exchangeEnabled).toBe(true));
    expect(get).toHaveBeenCalledWith(FEATURES_URL);
    expect(FEATURES_URL).toMatch(/\/api\/config\/features\/$/);
    expect(FEATURES_URL).not.toContain("/v1/");
  });

  it("troc éteint quand le serveur répond false", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { features: { exchange_enabled: false } } });
    const { result } = renderHook(() => useFeatures(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.exchangeEnabled).toBe(false);
  });

  it("repli sûr : troc éteint pendant le chargement", () => {
    vi.spyOn(apiClient, "get").mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useFeatures(), { wrapper });
    expect(result.current.exchangeEnabled).toBe(false);
  });

  it("repli sûr : troc éteint si l'appel échoue, sans nouvelle tentative", async () => {
    const get = vi.spyOn(apiClient, "get").mockRejectedValue(Object.assign(new Error("réseau"), { response: { status: 500 } }));
    const { result } = renderHook(() => useFeatures(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.exchangeEnabled).toBe(false);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("repli sûr : un corps inattendu ne rallume pas le troc", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { features: { exchange_enabled: "true" } } });
    const { result } = renderHook(() => useFeatures(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.exchangeEnabled).toBe(false);
  });

  it("durée de fraîcheur de 60 s, alignée sur Cache-Control", () => {
    expect(FEATURES_STALE_TIME_MS).toBe(60_000);
  });
});
