import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { OrganizationMember } from "@/api/types";
import { contextsKeys } from "./use-contexts";
import { organizationKeys } from "./use-organizations";
import { teamKeys, useChangeMemberRole, useMembers, useRemoveMember, useTransferOwnership } from "./use-organization-team";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const ORG = "11111111-1111-4111-8111-111111111111";
const M1 = "22222222-2222-4222-8222-222222222222";
const M2 = "33333333-3333-4333-8333-333333333333";
const member = (id: string, role: OrganizationMember["role"] = "EDITOR"): OrganizationMember => ({
  membership_id: id,
  display_name: "Marie K.",
  role,
  joined_at: "2026-11-09T08:00:00Z",
  is_self: false,
  is_last_effective_owner: null,
});
const page = (results: OrganizationMember[], next: string | null = null) => ({ count: results.length, next, previous: null, results });

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };

afterEach(() => vi.restoreAllMocks());

describe("useMembers", () => {
  it("lit la première page sans paramètre, puis ?page=2 ; dédoublonne par membership_id", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ data: page([member(M1)], "http://x/?page=2") })
      .mockResolvedValueOnce({ data: page([member(M1), member(M2)]) });
    const { result } = renderHook(() => useMembers(ORG), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith(`accounts/organizations/${ORG}/members/`, { params: undefined });
    expect(result.current.hasNextPage).toBe(true);
    await act(async () => {
      await result.current.fetchNextPage();
    });
    expect(get).toHaveBeenLastCalledWith(`accounts/organizations/${ORG}/members/`, { params: { page: 2 } });
    await waitFor(() => expect(result.current.data?.members.map((m) => m.membership_id)).toEqual([M1, M2]));
    expect(result.current.hasNextPage).toBe(false);
  });

  it("ne lit rien sans identifiant d'organisation", () => {
    const get = vi.spyOn(apiClient, "get");
    renderHook(() => useMembers(undefined), { wrapper: wrapperFor(newClient()) });
    expect(get).not.toHaveBeenCalled();
  });

  it("la clé de requête ne contient que l'organisation (aucun identifiant de membre ni secret)", () => {
    expect(teamKeys.members(ORG)).toEqual(["organizations", "members", ORG]);
  });
});

describe("mutations d'équipe", () => {
  let client: QueryClient;
  let invalidate: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    client = newClient();
    invalidate = vi.spyOn(client, "invalidateQueries");
  });
  const invalidated = () => invalidate.mock.calls.map((call) => JSON.stringify((call[0] as { queryKey: unknown }).queryKey));

  it("changement de rôle : PATCH sur le membre avec le corps tel quel, liste rechargée", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: member(M1, "ADMIN") });
    const { result } = renderHook(() => useChangeMemberRole(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ membershipId: M1, body: { role: "ADMIN" } });
    });
    expect(patch).toHaveBeenCalledWith(`accounts/organizations/${ORG}/members/${M1}/`, { role: "ADMIN" });
    expect(invalidated()).toContain(JSON.stringify(teamKeys.members(ORG)));
  });

  it("le mot de passe ne voyage que dans le corps : jamais dans l'URL, ni dans une clé de requête", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: member(M1, "OWNER") });
    const { result } = renderHook(() => useChangeMemberRole(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ membershipId: M1, body: { role: "OWNER", confirm: true, password: "s3cret-Pass" } });
    });
    const [url, body] = patch.mock.calls[0];
    expect(url).not.toContain("s3cret-Pass");
    expect(body).toEqual({ role: "OWNER", confirm: true, password: "s3cret-Pass" });
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.queryKey))).not.toContain("s3cret-Pass");
    expect(JSON.stringify(invalidated())).not.toContain("s3cret-Pass");
  });

  it("retrait : DELETE sans corps, listes des membres et des invitations rechargées", async () => {
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ status: 204, data: "" });
    const { result } = renderHook(() => useRemoveMember(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync(M1);
    });
    expect(del).toHaveBeenCalledWith(`accounts/organizations/${ORG}/members/${M1}/`);
    expect(invalidated()).toEqual(expect.arrayContaining([JSON.stringify(teamKeys.members(ORG)), JSON.stringify(teamKeys.invitations(ORG))]));
  });

  it("transfert : POST transfer-ownership, puis membres, organisation (my_role) et profils rechargés", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { new_owner: member(M1, "OWNER"), me: member(M2, "ADMIN") } });
    const { result } = renderHook(() => useTransferOwnership(ORG), { wrapper: wrapperFor(client) });
    const body = { membership_id: M1, my_new_role: "ADMIN" as const, confirm: true as const, password: "s3cret-Pass" };
    await act(async () => {
      await result.current.mutateAsync(body);
    });
    expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/transfer-ownership/`, body);
    expect(invalidated()).toEqual(
      expect.arrayContaining([
        JSON.stringify(teamKeys.members(ORG)),
        JSON.stringify(organizationKeys.internal(ORG)),
        JSON.stringify(contextsKeys.all),
      ]),
    );
  });

  it("aucune relance automatique d'un POST, et la mutation ne reste pas en cache (gcTime 0)", async () => {
    const post = vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 500, data: {} } });
    const { result } = renderHook(() => useTransferOwnership(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ membership_id: M1, my_new_role: "ADMIN", confirm: true, password: "x" }).catch(() => undefined);
    });
    expect(post).toHaveBeenCalledTimes(1);
    expect(client.getMutationCache().getAll().every((m) => m.gcTime === 0)).toBe(true);
  });

  it("refus DENY_PERMISSION : liste et rôle de l'acteur rechargés ; member_not_found : liste rechargée", async () => {
    vi.spyOn(apiClient, "patch").mockRejectedValueOnce({ response: { status: 403, data: { code: "DENY_PERMISSION" } } });
    const { result } = renderHook(() => useChangeMemberRole(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ membershipId: M1, body: { role: "ADMIN" } }).catch(() => undefined);
    });
    expect(invalidated()).toEqual(expect.arrayContaining([JSON.stringify(teamKeys.members(ORG)), JSON.stringify(organizationKeys.internal(ORG))]));

    invalidate.mockClear();
    vi.spyOn(apiClient, "patch").mockRejectedValueOnce({ response: { status: 404, data: { code: "member_not_found" } } });
    await act(async () => {
      await result.current.mutateAsync({ membershipId: M1, body: { role: "ADMIN" } }).catch(() => undefined);
    });
    expect(invalidated()).toEqual([JSON.stringify(teamKeys.members(ORG))]);
  });

  it("une erreur de validation (400) ne recharge rien", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 400, data: { code: "password_required" } } });
    const { result } = renderHook(() => useTransferOwnership(ORG), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ membership_id: M1, my_new_role: "ADMIN", confirm: true, password: "x" }).catch(() => undefined);
    });
    expect(invalidate).not.toHaveBeenCalled();
  });
});
