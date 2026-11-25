import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import { clearInvitationToken, readInvitationToken, storeInvitationToken } from "@/lib/invitation-token";
import { contextsKeys } from "./use-contexts";
import {
  INVITATION_PREVIEW_KEY,
  teamKeys,
  useAcceptInvitation,
  useCreateInvitation,
  useDeclineInvitation,
  useInvitationPreview,
  useInvitations,
  useRevokeInvitation,
} from "./use-organization-team";

const auth = vi.hoisted(() => ({ isAuthenticated: true, user: { id: "compte-A" } as { id: string } | null }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

const ORG = "11111111-1111-4111-8111-111111111111";
const M1 = "22222222-2222-4222-8222-222222222222";
const INV = "44444444-4444-4444-8444-444444444444";
const TOKEN = "tok_ABC-123_secretsecretsecretsecretsecret00";
const invitation = (id = INV) => ({
  invitation_id: id,
  role: "EDITOR" as const,
  status: "PENDING" as const,
  label: "Jean, comptable",
  created_at: "2026-11-09T08:00:00Z",
  expires_at: "2026-11-16T08:00:00Z",
  created_by_display_name: "Paul M.",
  is_mine: true,
});

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
const keysOf = (spy: ReturnType<typeof vi.spyOn>) => spy.mock.calls.map((call) => JSON.stringify((call[0] as { queryKey: unknown }).queryKey));

afterEach(() => vi.restoreAllMocks());

describe("useInvitations", () => {
  it("ne part pas tant que l'onglet n'est pas ouvert (enabled faux)", () => {
    const get = vi.spyOn(apiClient, "get");
    renderHook(() => useInvitations(ORG, false), { wrapper: wrapperFor(newClient()) });
    expect(get).not.toHaveBeenCalled();
  });

  it("lit les invitations en attente, page 1 puis ?page=2, et dédoublonne", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ data: { count: 2, next: "http://x/?page=2", previous: null, results: [invitation()] } })
      .mockResolvedValueOnce({
        data: { count: 2, next: null, previous: null, results: [invitation(), invitation("55555555-5555-4555-8555-555555555555")] },
      });
    const { result } = renderHook(() => useInvitations(ORG), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/`, { params: { status: "PENDING" } });
    expect(get).toHaveBeenCalledTimes(1);
    expect(result.current.hasNextPage).toBe(true);
    await act(async () => {
      await result.current.fetchNextPage();
    });
    expect(get).toHaveBeenLastCalledWith(`accounts/organizations/${ORG}/invitations/`, { params: { status: "PENDING", page: 2 } });
    await waitFor(() => expect(result.current.data?.invitations.map((i) => i.invitation_id)).toEqual([INV, "55555555-5555-4555-8555-555555555555"]));
  });
});

describe("création et révocation d'invitation", () => {
  let client: QueryClient;
  let invalidate: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    client = newClient();
    invalidate = vi.spyOn(client, "invalidateQueries");
  });

  it("création : POST du corps tel quel, liste des invitations rechargée", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { ...invitation(), link_token: TOKEN } });
    const { result } = renderHook(() => useCreateInvitation(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ role: "EDITOR", label: "Jean, comptable" });
    });
    expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/`, { role: "EDITOR", label: "Jean, comptable" });
    expect(keysOf(invalidate)).toContain(JSON.stringify(teamKeys.invitations(ORG)));
  });

  it("le jeton créé ne reste ni dans le cache de requêtes, ni dans une clé, ni dans le cache de mutations après démontage", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: { ...invitation(), link_token: TOKEN } });
    const { result, unmount } = renderHook(() => useCreateInvitation(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ role: "ANALYST" });
    });
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => [q.queryKey, q.state.data]))).not.toContain(TOKEN);
    expect(JSON.stringify(keysOf(invalidate))).not.toContain(TOKEN);
    const mutations = client.getMutationCache().getAll();
    expect(mutations.length).toBeGreaterThan(0);
    expect(mutations.every((m) => m.gcTime === 0)).toBe(true);
    unmount();
    await waitFor(() => expect(client.getMutationCache().getAll()).toHaveLength(0));
  });

  it("création : aucune relance automatique d'un échec", async () => {
    const post = vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 500, data: {} } });
    const { result } = renderHook(() => useCreateInvitation(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ role: "EDITOR" }).catch(() => undefined);
    });
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("révocation : DELETE sur l'invitation, liste rechargée ; 409 invitation_not_pending recharge aussi", async () => {
    const del = vi.spyOn(apiClient, "delete").mockResolvedValueOnce({ status: 204, data: "" });
    const { result } = renderHook(() => useRevokeInvitation(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync(INV);
    });
    expect(del).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/${INV}/`);
    expect(keysOf(invalidate)).toContain(JSON.stringify(teamKeys.invitations(ORG)));

    invalidate.mockClear();
    vi.spyOn(apiClient, "delete").mockRejectedValueOnce({ response: { status: 409, data: { code: "invitation_not_pending" } } });
    await act(async () => {
      await result.current.mutateAsync(INV).catch(() => undefined);
    });
    expect(keysOf(invalidate)).toEqual([JSON.stringify(teamKeys.invitations(ORG))]);
  });
});

describe("échange du jeton (aperçu, acceptation, refus)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    storeInvitationToken(TOKEN);
  });
  afterEach(() => clearInvitationToken());

  const PREVIEW = {
    organization_name: "Boutique Lumière",
    org_type: "ENTREPRISE",
    role: "EDITOR",
    expires_at: "2026-11-16T08:00:00Z",
    invited_by_display_name: "Paul M.",
  };

  it("aperçu : POST dans le CORPS, URL sans jeton, clé sans jeton, jamais conservé (gcTime 0)", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: PREVIEW });
    const client = newClient();
    const { result } = renderHook(() => useInvitationPreview(true), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(post).toHaveBeenCalledWith("accounts/organization-invitations/preview/", { token: TOKEN });
    expect(post.mock.calls[0][0]).not.toContain(TOKEN);
    expect(INVITATION_PREVIEW_KEY).toEqual(["org-invitation-preview"]);
    const queries = client.getQueryCache().getAll();
    expect(queries.map((q) => q.queryKey)).toEqual([INVITATION_PREVIEW_KEY]);
    expect(JSON.stringify(queries.map((q) => q.queryKey))).not.toContain(TOKEN);
    expect(queries[0].gcTime).toBe(0);
  });

  it("aperçu : désactivé, il n'appelle rien ; 404 : jamais relancé même avec les réglages par défaut", async () => {
    const post = vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 404, data: { code: "invitation_invalid" } } });
    renderHook(() => useInvitationPreview(false), { wrapper: wrapperFor(newClient()) });
    expect(post).not.toHaveBeenCalled();
    const { result } = renderHook(() => useInvitationPreview(true), { wrapper: wrapperFor(new QueryClient()) });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("acceptation : POST du jeton relu dans le stockage (jamais une variable de mutation), jeton effacé, profils rechargés", async () => {
    const accepted = { organization_id: ORG, organization_name: "Boutique Lumière", role: "EDITOR", membership_id: M1 };
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: accepted });
    const client = newClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useAcceptInvitation(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync();
    });
    expect(post).toHaveBeenCalledWith("accounts/organization-invitations/accept/", { token: TOKEN });
    expect(post.mock.calls[0][0]).not.toContain(TOKEN);
    expect(client.getMutationCache().getAll().every((m) => m.state.variables === undefined)).toBe(true);
    expect(readInvitationToken()).toBeNull();
    expect(keysOf(invalidate)).toContain(JSON.stringify(contextsKeys.all));
  });

  it("acceptation en échec : le jeton reste rangé, aucune relance", async () => {
    const post = vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 403, data: { code: "phone_verification_required" } } });
    const { result } = renderHook(() => useAcceptInvitation(), { wrapper: wrapperFor(newClient()) });
    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });
    expect(post).toHaveBeenCalledTimes(1);
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("refus : POST du jeton dans le corps, jeton effacé au succès", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ status: 204, data: "" });
    const { result } = renderHook(() => useDeclineInvitation(), { wrapper: wrapperFor(newClient()) });
    await act(async () => {
      await result.current.mutateAsync();
    });
    expect(post).toHaveBeenCalledWith("accounts/organization-invitations/decline/", { token: TOKEN });
    expect(readInvitationToken()).toBeNull();
  });

  it("sans jeton rangé, aucun appel réseau n'est fait", async () => {
    clearInvitationToken();
    const post = vi.spyOn(apiClient, "post");
    const { result } = renderHook(() => useAcceptInvitation(), { wrapper: wrapperFor(newClient()) });
    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });
    expect(post).not.toHaveBeenCalled();
  });

  it("acceptation : la promesse ne se résout qu'après le rechargement des profils (nouveau profil sélectionnable)", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: { organization_id: ORG, organization_name: "B", role: "EDITOR", membership_id: M1 } });
    const client = newClient();
    let release: () => void = () => undefined;
    vi.spyOn(client, "invalidateQueries").mockReturnValue(new Promise<void>((resolve) => (release = resolve)));
    const { result } = renderHook(() => useAcceptInvitation(), { wrapper: wrapperFor(client) });
    let done = false;
    const pending = act(async () => {
      await result.current.mutateAsync();
      done = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(done).toBe(false);
    release();
    await pending;
    expect(done).toBe(true);
  });

  describe("jeton lié au compte (audit S2)", () => {
    afterEach(() => {
      auth.user = { id: "compte-A" };
    });

    it("l'aperçu réussi lie le jeton au compte : un autre compte ne peut plus s'en servir, il est effacé", async () => {
      auth.user = { id: "compte-A" };
      const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: PREVIEW });
      const { result } = renderHook(() => useInvitationPreview(true), { wrapper: wrapperFor(newClient()) });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(readInvitationToken("compte-A")).toBe(TOKEN);

      auth.user = { id: "compte-B" };
      post.mockClear();
      const accept = renderHook(() => useAcceptInvitation(), { wrapper: wrapperFor(newClient()) });
      await act(async () => {
        await accept.result.current.mutateAsync().catch(() => undefined);
      });
      expect(post).not.toHaveBeenCalled();
      expect(readInvitationToken()).toBeNull();
    });

    it("le même compte garde son jeton après l'aperçu", async () => {
      auth.user = { id: "compte-A" };
      vi.spyOn(apiClient, "post").mockResolvedValue({ data: PREVIEW });
      const { result } = renderHook(() => useInvitationPreview(true), { wrapper: wrapperFor(newClient()) });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(readInvitationToken("compte-A")).toBe(TOKEN);
    });
  });

  it("compte inconnu : ni aperçu, ni acceptation, ni refus (le jeton ne peut être lié à personne)", async () => {
    auth.user = null;
    const post = vi.spyOn(apiClient, "post");
    const { result } = renderHook(() => useInvitationPreview(true), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const accept = renderHook(() => useAcceptInvitation(), { wrapper: wrapperFor(newClient()) });
    const decline = renderHook(() => useDeclineInvitation(), { wrapper: wrapperFor(newClient()) });
    await act(async () => {
      await accept.result.current.mutateAsync().catch(() => undefined);
      await decline.result.current.mutateAsync().catch(() => undefined);
    });
    expect(post).not.toHaveBeenCalled();
    expect(readInvitationToken()).toBe(TOKEN);
    auth.user = { id: "compte-A" };
  });
});
