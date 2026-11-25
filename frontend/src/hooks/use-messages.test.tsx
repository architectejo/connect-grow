import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import apiClient from "@/api/client";
import { MESSAGES_POLL_MS, messagesRefetchInterval, useConversationMessages, useConversations } from "./use-messages";

const failure = (status: number, headers: Record<string, string> = {}) => ({ response: { status, data: {}, headers } });

describe("messagesRefetchInterval", () => {
  it("interroge toutes les 5 s en situation normale", () => {
    expect(messagesRefetchInterval(null)).toBe(MESSAGES_POLL_MS);
  });

  it.each([401, 403, 404])("arrête l'interrogation sur un %i", (status) => {
    expect(messagesRefetchInterval(failure(status))).toBe(false);
  });

  it("suspend l'interrogation pendant Retry-After sur un 429", () => {
    expect(messagesRefetchInterval(failure(429, { "retry-after": "45" }))).toBe(45_000);
  });

  it("applique une pause par défaut sans Retry-After", () => {
    expect(messagesRefetchInterval(failure(429))).toBe(30_000);
  });

  it("reprend le rythme normal après une panne passagère", () => {
    expect(messagesRefetchInterval(failure(503))).toBe(MESSAGES_POLL_MS);
  });
});

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

describe("hooks de messagerie", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lit les conversations en tableau ou en enveloppe paginée sans rien perdre", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: { count: 1, next: null, previous: null, results: [{ id: "c1" }] } });
    const { result } = renderHook(() => useConversations(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual([{ id: "c1" }]));
    // jamais de ?page ni ?page_size : l'API renvoie alors un simple tableau
    expect(get).toHaveBeenCalledWith("interactions/conversations/");
  });

  it("signale la pause d'actualisation sur un 429 sans relancer la requête", async () => {
    const get = vi.spyOn(apiClient, "get").mockRejectedValue(failure(429, { "retry-after": "60" }));
    const { result } = renderHook(() => useConversationMessages("c1"), { wrapper });
    await waitFor(() => expect(result.current.isPaused).toBe(true));
    expect(get).toHaveBeenCalledTimes(1);
  });
});
