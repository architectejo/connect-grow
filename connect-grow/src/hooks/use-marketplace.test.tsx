import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import apiClient from "@/api/client";
import { businessesRequestParams, useBusinesses } from "./use-marketplace";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);

const business = (id: string) => ({ id, business_name: `Boutique ${id}`, is_verified: false });

describe("businessesRequestParams", () => {
  it("envoie is_verified=true au serveur quand le filtre est actif", () => {
    expect(businessesRequestParams("kin", true, 2)).toEqual({ search: "kin", is_verified: "true", page: 2 });
  });

  it("n'envoie ni is_verified ni recherche vide sinon", () => {
    expect(businessesRequestParams("", false, 1)).toEqual({ page: 1 });
  });
});

describe("useBusinesses (liste paginée)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("charge la première page puis la suivante, avec des identifiants UUID en chaîne", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ data: { count: 3, next: "http://x/?page=2", previous: null, results: [business("a1"), business("b2")] } })
      .mockResolvedValueOnce({ data: { count: 3, next: null, previous: "http://x/", results: [business("c3")] } });

    const { result } = renderHook(() => useBusinesses("kin"), { wrapper });
    await waitFor(() => expect(result.current.data?.businesses).toHaveLength(2));
    expect(result.current.data?.count).toBe(3);
    expect(result.current.hasNextPage).toBe(true);
    expect(get).toHaveBeenNthCalledWith(1, "accounts/businesses/", { params: { search: "kin", page: 1 } });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(get).toHaveBeenNthCalledWith(2, "accounts/businesses/", { params: { search: "kin", page: 2 } });
    await waitFor(() => expect(result.current.data?.businesses.map((b) => b.id)).toEqual(["a1", "b2", "c3"]));
    expect(result.current.hasNextPage).toBe(false);
  });
});
