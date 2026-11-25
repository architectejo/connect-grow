import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import { contextsKeys } from "./use-contexts";
import { isProviderNotFound, providerKeys, useActivateProvider, useArchiveProvider, useProvider, useUpdateProvider } from "./use-provider";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
const PROFILE = { id: "p1", display_name: "Marie couture", bio: "", category_ids: [], status: "ACTIVE", created_at: "2026-10-10T10:00:00Z" };
const notFound = { response: { status: 404, data: { detail: "x", code: "provider_not_found" } } };

describe("profil prestataire", () => {
  afterEach(() => vi.restoreAllMocks());

  it("404 provider_not_found = non activé : un état normal (null), pas une erreur", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(notFound);
    const { result } = renderHook(() => useProvider(), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it("une autre erreur (500, ou 404 sans le code) reste une erreur", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({ response: { status: 500, data: {} } });
    const { result } = renderHook(() => useProvider(), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect(isProviderNotFound({ response: { status: 404, data: { code: "autre" } } })).toBe(false);
    expect(isProviderNotFound(notFound)).toBe(true);
  });

  it("activation : le nom public est envoyé tel que confirmé ; 201 = créé, 200 = déjà actif ou réactivé", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce({ status: 201, data: PROFILE }).mockResolvedValueOnce({ status: 200, data: PROFILE });
    const client = newClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useActivateProvider(), { wrapper: wrapperFor(client) });
    let first: { created: boolean } | undefined;
    await act(async () => {
      first = await result.current.mutateAsync({ display_name: "Marie couture", bio: "" });
    });
    expect(post).toHaveBeenCalledWith("accounts/provider/activate/", { display_name: "Marie couture", bio: "" });
    expect(first?.created).toBe(true);
    let second: { created: boolean } | undefined;
    await act(async () => {
      second = await result.current.mutateAsync({});
    });
    expect(second?.created).toBe(false);
    expect(client.getQueryData(providerKeys.all)).toEqual(PROFILE);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: contextsKeys.all });
  });

  it("modification (PATCH) et désactivation (POST archive/) mettent le cache à jour", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: { ...PROFILE, bio: "Couture" } });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { ...PROFILE, status: "ARCHIVED" } });
    const client = newClient();
    const update = renderHook(() => useUpdateProvider(), { wrapper: wrapperFor(client) });
    await act(() => update.result.current.mutateAsync({ bio: "Couture" }));
    expect(patch).toHaveBeenCalledWith("accounts/provider/", { bio: "Couture" });
    const archive = renderHook(() => useArchiveProvider(), { wrapper: wrapperFor(client) });
    await act(() => archive.result.current.mutateAsync());
    expect(post).toHaveBeenCalledWith("accounts/provider/archive/");
    expect((client.getQueryData(providerKeys.all) as { status: string }).status).toBe("ARCHIVED");
  });
});
