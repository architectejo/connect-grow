import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import { useReceivedReveals, useRevealContact } from "./use-contact-reveal";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };

const row = (n: number) => ({
  id: `00000000-0000-4000-8000-00000000000${n}`,
  channel: "CALL" as const,
  created_at: "2026-10-10T09:12:00Z",
  requester_display_name: "Marie K.",
  offer: { id: "11111111-1111-4111-8111-111111111111", title: "Chaussures" },
});

describe("useRevealContact", () => {
  afterEach(() => vi.restoreAllMocks());

  it("POST {offer, channel} et ne laisse rien dans le cache des requêtes", async () => {
    const data = { contact_event_id: "x", channel: "CALL", created: true, phone: "+243812345678", tel_url: "tel:+243812345678", whatsapp_url: null };
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data });
    const client = newClient();
    const { result } = renderHook(() => useRevealContact(), { wrapper: wrapperFor(client) });
    await act(() => result.current.mutateAsync({ offer: "o1", channel: "CALL" }));
    expect(post).toHaveBeenCalledWith("interactions/contacts/reveal/", { offer: "o1", channel: "CALL" });
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    act(() => result.current.reset());
    expect(result.current.data).toBeUndefined();
  });

  it("n'est pas relancé automatiquement après une erreur", async () => {
    const post = vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 409, data: { code: "reveal_in_progress" } } });
    const { result } = renderHook(() => useRevealContact(), { wrapper: wrapperFor(newClient()) });
    await act(() => result.current.mutateAsync({ offer: "o1", channel: "CALL" }).catch(() => undefined));
    expect(post).toHaveBeenCalledTimes(1);
  });
});

describe("useReceivedReveals", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lit la liste paginée, filtre par canal et charge la page suivante", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ data: { count: 2, next: "http://x/?page=2", previous: null, results: [row(1)] } })
      .mockResolvedValueOnce({ data: { count: 2, next: null, previous: null, results: [row(2)] } });
    const { result } = renderHook(() => useReceivedReveals("CALL"), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.data?.reveals).toHaveLength(1));
    expect(get).toHaveBeenCalledWith("interactions/contacts/reveals/received/", { params: { channel: "CALL", page: 1 } });
    await act(() => result.current.fetchNextPage());
    await waitFor(() => expect(result.current.data?.reveals).toHaveLength(2));
    expect(get).toHaveBeenLastCalledWith("interactions/contacts/reveals/received/", { params: { channel: "CALL", page: 2 } });
    expect(result.current.hasNextPage).toBe(false);
  });

  it("sans filtre, n'envoie pas de paramètre channel", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: { count: 0, next: null, previous: null, results: [] } });
    renderHook(() => useReceivedReveals(), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(get).toHaveBeenCalledWith("interactions/contacts/reveals/received/", { params: { page: 1 } });
  });
});
