import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import apiClient from "@/api/client";
import { organizationsRequestParams, useOrganizationDirectory, useSellerProfile } from "./use-marketplace";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);

const organization = (id: string) => ({
  id,
  name: `Organisation ${id}`,
  org_type: "BOUTIQUE",
  description: "",
  logo: null,
  city_id: null,
  commune_id: null,
  category_ids: [],
  verified_claims: [],
  verification_summary: { complete: false, label: null },
  member_since: "2026-09-01T09:00:00+01:00",
});

describe("organizationsRequestParams", () => {
  it("envoie tous les filtres au serveur (aucun filtrage local)", () => {
    expect(organizationsRequestParams({ search: "kin", org_type: "ONG", claim: "RCCM_VERIFIED", fully_verified: true }, 2)).toEqual({
      search: "kin",
      org_type: "ONG",
      claim: "RCCM_VERIFIED",
      fully_verified: "true",
      page: 2,
    });
  });

  it("n'envoie ni filtre vide ni fully_verified à faux", () => {
    expect(organizationsRequestParams({ search: "", org_type: "", claim: "", fully_verified: false }, 1)).toEqual({ page: 1 });
  });

  it("n'envoie aucun paramètre de tri ni de promotion (tri alphabétique côté serveur, règles 3 et 5)", () => {
    const keys = Object.keys(organizationsRequestParams({ search: "a", org_type: "ONG", claim: "RCCM_VERIFIED", fully_verified: true }, 1));
    expect(keys.sort()).toEqual(["claim", "fully_verified", "org_type", "page", "search"]);
  });
});

describe("useOrganizationDirectory (liste paginée)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("charge la première page puis la suivante depuis accounts/organizations/", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ data: { count: 3, next: "http://x/?page=2", previous: null, results: [organization("a1"), organization("b2")] } })
      .mockResolvedValueOnce({ data: { count: 3, next: null, previous: "http://x/", results: [organization("c3")] } });

    const { result } = renderHook(() => useOrganizationDirectory({ search: "kin" }), { wrapper });
    await waitFor(() => expect(result.current.data?.organizations).toHaveLength(2));
    expect(result.current.data?.count).toBe(3);
    expect(result.current.hasNextPage).toBe(true);
    expect(get).toHaveBeenNthCalledWith(1, "accounts/organizations/", { params: { search: "kin", page: 1 } });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(get).toHaveBeenNthCalledWith(2, "accounts/organizations/", { params: { search: "kin", page: 2 } });
    await waitFor(() => expect(result.current.data?.organizations.map((o) => o.id)).toEqual(["a1", "b2", "c3"]));
    expect(result.current.hasNextPage).toBe(false);
  });
});

describe("useSellerProfile", () => {
  afterEach(() => vi.restoreAllMocks());

  it("appelle marketplace/sellers/<type en minuscules>/<id>/", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: { context_type: "PROVIDER", context_id: "p1", display_name: "Marie couture" } });
    const { result } = renderHook(() => useSellerProfile("PROVIDER", "p1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith("marketplace/sellers/provider/p1/");
  });

  it("n'appelle rien sans type ni identifiant", () => {
    const get = vi.spyOn(apiClient, "get");
    renderHook(() => useSellerProfile(undefined, undefined), { wrapper });
    expect(get).not.toHaveBeenCalled();
  });
});
