import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import axios from "axios";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import apiClient, { resetRefreshState } from "@/api/client";
import { POST_DRAFT_KEY } from "@/lib/tokens";
import { tokenStorage } from "@/lib/tokens";
import { AuthProvider, useAuth } from "./AuthContext";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <AuthProvider>{children}</AuthProvider>
  </QueryClientProvider>
);

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

describe("déconnexion", () => {
  beforeEach(() => {
    localStorage.clear();
    resetRefreshState();
    vi.mocked(toast.error).mockClear();
    tokenStorage.set("acces-1", "refresh-1");
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { id: "u-1", full_name: "Test" } });
  });
  afterEach(() => vi.restoreAllMocks());

  it("appelle accounts/logout/ avec le refresh token, puis purge la session", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => result.current.logout());

    expect(post).toHaveBeenCalledWith("accounts/logout/", { refresh: "refresh-1" }, { headers: { Authorization: "Bearer acces-1" } });
    expect(tokenStorage.getAccess()).toBeNull();
    expect(tokenStorage.getRefresh()).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("déconnecte tous les appareils sur demande", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => result.current.logout({ all: true }));

    expect(post).toHaveBeenCalledWith("accounts/logout-all/", { refresh: "refresh-1" }, expect.anything());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("logout-all : sur 401, un seul rafraîchissement puis un seul rejeu", async () => {
    vi.spyOn(axios, "post").mockResolvedValue({ data: { access: "acces-2", refresh: "refresh-2" } });
    const post = vi
      .spyOn(apiClient, "post")
      .mockRejectedValueOnce({ response: { status: 401 } })
      .mockResolvedValueOnce({ data: {} });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => result.current.logout({ all: true }));

    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledTimes(2);
    expect(post).toHaveBeenLastCalledWith("accounts/logout-all/", { refresh: "refresh-2" }, { headers: { Authorization: "Bearer acces-2" } });
    expect(toast.error).not.toHaveBeenCalled();
    expect(tokenStorage.getAccess()).toBeNull();
  });

  it("logout-all : si le rejeu échoue, prévient que seule la déconnexion locale a eu lieu", async () => {
    vi.spyOn(axios, "post").mockResolvedValue({ data: { access: "acces-2", refresh: "refresh-2" } });
    const post = vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 401 } });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => result.current.logout({ all: true }));

    expect(post).toHaveBeenCalledTimes(2); // jamais plus d'un rejeu
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Déconnexion locale uniquement"));
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("logout-all : un refresh impossible est signalé, pas avalé", async () => {
    vi.spyOn(axios, "post").mockRejectedValue({ response: { status: 401 } });
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 401 } });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => result.current.logout({ all: true }));

    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it("endSession purge localement sans appeler le serveur", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    act(() => result.current.endSession());

    expect(post).not.toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("autre onglet : le jeton retiré déclenche la purge complète (brouillon, session)", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());
    localStorage.setItem(POST_DRAFT_KEY, "{}");

    localStorage.removeItem("access_token"); // fait par l'autre onglet
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "access_token", newValue: null }));
    });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(false));
    expect(result.current.user).toBeNull();
    expect(localStorage.getItem(POST_DRAFT_KEY)).toBeNull();
  });

  it("se déconnecte localement même si le serveur répond une erreur", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 429 } });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());

    await act(async () => result.current.logout());

    await waitFor(() => expect(result.current.isAuthenticated).toBe(false));
    expect(tokenStorage.getRefresh()).toBeNull();
  });
});
