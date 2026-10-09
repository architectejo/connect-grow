import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "@/api/client";
import { tokenStorage } from "@/lib/tokens";
import { AuthProvider, useAuth } from "./AuthContext";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <AuthProvider>{children}</AuthProvider>
  </QueryClientProvider>
);

describe("déconnexion", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStorage.set("acces-1", "refresh-1");
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { id: "u-1", full_name: "Test" } });
  });
  afterEach(() => vi.restoreAllMocks());

  it("appelle accounts/logout/ avec le refresh token, puis purge la session", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    act(() => result.current.logout());

    expect(post).toHaveBeenCalledWith("accounts/logout/", { refresh: "refresh-1" }, { headers: { Authorization: "Bearer acces-1" } });
    expect(tokenStorage.getAccess()).toBeNull();
    expect(tokenStorage.getRefresh()).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("déconnecte tous les appareils sur demande", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    act(() => result.current.logout({ all: true }));

    expect(post).toHaveBeenCalledWith("accounts/logout-all/", { refresh: "refresh-1" }, expect.anything());
  });

  it("se déconnecte localement même si le serveur répond une erreur", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 429 } });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    act(() => result.current.logout());

    await waitFor(() => expect(result.current.isAuthenticated).toBe(false));
    expect(tokenStorage.getRefresh()).toBeNull();
  });
});
