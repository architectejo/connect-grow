import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider, onlineManager } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import { teamKeys, useAwaitingConfirmations, useConfirmInvitation } from "./use-organization-team";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true, user: { id: "compte-A" } }) }));

// Délai propre à ce fichier (jsdom, machine de développement chargée)
vi.setConfig({ testTimeout: 20_000 });

const ORG = "11111111-1111-4111-8111-111111111111";
const INV = "44444444-4444-4444-8444-444444444444";
const NETWORK = { isAxiosError: true, message: "Network Error" };
const BODY = { confirm: true as const, password: "pw", code: "482913" };

const setup = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: { count: 0, next: null, previous: null, results: [] } });
  const post = vi.spyOn(apiClient, "post").mockRejectedValue(NETWORK);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  // La liste « À traiter » observe la requête : un rechargement est un nouvel appel GET
  const hook = renderHook(() => ({ list: useAwaitingConfirmations(ORG), confirm: useConfirmInvitation(ORG) }), { wrapper });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const invitationInvalidations = () =>
    invalidate.mock.calls.filter((c) => JSON.stringify(c[0]?.queryKey) === JSON.stringify(teamKeys.invitations(ORG))).length;
  return { get, post, hook, invitationInvalidations };
};

/**
 * Échec réseau sans réponse. La mutation part en ligne : React Query met en pause une mutation lancée hors ligne
 * (`networkMode: "online"`), la coupure est donc simulée APRÈS l'échec.
 */
const failByNetwork = async (hook: ReturnType<typeof setup>["hook"]) => {
  await act(async () => {
    await hook.result.current.confirm.mutateAsync({ invitationId: INV, body: BODY }).catch(() => undefined);
  });
};

afterEach(() => {
  onlineManager.setOnline(true);
  vi.restoreAllMocks();
});

describe("useConfirmInvitation : coupure réseau sans réponse (L1-01-F2bis)", () => {
  it("aucune relance de la mutation ; liste rechargée (GET) au retour du réseau, une seule fois", async () => {
    const { get, post, hook, invitationInvalidations } = setup();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    await failByNetwork(hook);
    expect(post).toHaveBeenCalledTimes(1);
    expect(invitationInvalidations()).toBe(0);
    act(() => onlineManager.setOnline(false));
    expect(invitationInvalidations()).toBe(0);
    act(() => onlineManager.setOnline(true));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(invitationInvalidations()).toBe(1);
    // Abonnement retiré : une nouvelle bascule ne recharge plus
    act(() => onlineManager.setOnline(false));
    act(() => onlineManager.setOnline(true));
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(invitationInvalidations()).toBe(1);
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("fermeture du dialogue (démontage) avant le retour du réseau : liste rechargée à la fermeture, plus d'abonnement ensuite", async () => {
    const { get, hook, invitationInvalidations } = setup();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    await failByNetwork(hook);
    act(() => onlineManager.setOnline(false));
    expect(invitationInvalidations()).toBe(0);
    hook.unmount();
    expect(invitationInvalidations()).toBe(1);
    act(() => onlineManager.setOnline(true));
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(invitationInvalidations()).toBe(1);
  });

  it("échec avec réponse du serveur (pas une coupure) : rien n'est rechargé à la fermeture", async () => {
    const { get, post, hook, invitationInvalidations } = setup();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    post.mockRejectedValue({ isAxiosError: true, response: { status: 403, data: { code: "reauthentication_failed", detail: "x" }, headers: {} } });
    await failByNetwork(hook);
    hook.unmount();
    expect(invitationInvalidations()).toBe(0);
  });
});
