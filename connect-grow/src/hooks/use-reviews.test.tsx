import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { Review } from "@/api/types";
import { reviewKeys, useReportFakeContact, useReviewEligibility, useReviewMutations } from "./use-reviews";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };

const review = (id: string, extra: Partial<Review> = {}): Review => ({
  id,
  post: "p1",
  is_mine: true,
  user_name: "Marie K.",
  offer_rating: 4,
  seller_rating: 5,
  content: "Très bon contact avec le vendeur.",
  source: "CONTACT",
  created_at: "2026-10-09T10:00:00+01:00",
  can_edit: true,
  ...extra,
});

describe("useReviewEligibility", () => {
  afterEach(() => vi.restoreAllMocks());

  it("interroge le serveur et ne déduit rien côté client", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { can_review: false, reason: "too_early", available_at: "2026-10-10T13:05:00Z", review_id: null },
    });
    const { result } = renderHook(() => useReviewEligibility("p1", "u1"), { wrapper: wrapperFor(newClient()) });
    await waitFor(() => expect(result.current.data?.reason).toBe("too_early"));
    expect(get).toHaveBeenCalledWith("interactions/reviews/eligibility/", { params: { post: "p1" } });
  });

  it("ne lance aucune requête pour un anonyme (endpoint authentifié)", () => {
    const get = vi.spyOn(apiClient, "get");
    renderHook(() => useReviewEligibility("p1", undefined), { wrapper: wrapperFor(newClient()) });
    expect(get).not.toHaveBeenCalled();
  });

  it("ne lance aucune requête quand il est désactivé (vendeur de l'offre)", () => {
    const get = vi.spyOn(apiClient, "get");
    renderHook(() => useReviewEligibility("p1", "u1", false), { wrapper: wrapperFor(newClient()) });
    expect(get).not.toHaveBeenCalled();
  });

  it("sépare les réponses de deux comptes dans le cache", () => {
    expect(reviewKeys.eligibility("p1", "u1")).not.toEqual(reviewKeys.eligibility("p1", "u2"));
    expect(reviewKeys.eligibility("p1")).toEqual(["reviews", "eligibility", "p1", "anonymous"]);
  });
});

describe("useReviewMutations", () => {
  afterEach(() => vi.restoreAllMocks());

  it("crée un avis avec les deux notes, l'ajoute à la liste et relit les notes de l'offre", async () => {
    const created = review("r1");
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: created });
    const client = newClient();
    client.setQueryData(reviewKeys.forPost("p1"), [review("r0", { is_mine: false })]);
    const invalidate = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useReviewMutations("p1"), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.create.mutateAsync({ offer_rating: 4, seller_rating: 5, content: "Très bon contact avec le vendeur." });
    });

    expect(post).toHaveBeenCalledWith("interactions/reviews/", {
      post: "p1",
      offer_rating: 4,
      seller_rating: 5,
      content: "Très bon contact avec le vendeur.",
    });
    expect(client.getQueryData<Review[]>(reviewKeys.forPost("p1"))?.map((r) => r.id)).toEqual(["r1", "r0"]);
    const keys = invalidate.mock.calls.map(([filters]) => (filters as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["marketplace", "post", "p1"]);
    expect(keys).toContainEqual(reviewKeys.eligibilityOf("p1"));
  });

  it("après 409 already_reviewed, relit l'éligibilité au lieu de se fier à l'écran", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({
      response: { status: 409, data: { detail: "Vous avez déjà donné votre avis pour cette annonce.", code: "already_reviewed" } },
    });
    const client = newClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useReviewMutations("p1"), { wrapper: wrapperFor(client) });

    await act(async () => {
      await result.current.create.mutateAsync({ offer_rating: 4, seller_rating: 5, content: "Très bon contact." }).catch(() => {});
    });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: reviewKeys.eligibilityOf("p1") });
  });

  it("modifie par PATCH, supprime par DELETE et répond au bon endroit", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: review("r1", { edited_at: "2026-10-09T12:00:00+01:00" }) });
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ data: null });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: review("r1", { reply_content: "Merci !" }) });
    const client = newClient();
    client.setQueryData(reviewKeys.forPost("p1"), [review("r1")]);
    const { result } = renderHook(() => useReviewMutations("p1"), { wrapper: wrapperFor(client) });

    await act(async () => {
      await result.current.edit.mutateAsync({ id: "r1", offer_rating: 3, seller_rating: 3, content: "Un peu décevant, mais correct." });
    });
    expect(patch).toHaveBeenCalledWith("interactions/reviews/r1/", { offer_rating: 3, seller_rating: 3, content: "Un peu décevant, mais correct." });
    expect(client.getQueryData<Review[]>(reviewKeys.forPost("p1"))?.[0].edited_at).toBeTruthy();

    await act(async () => {
      await result.current.reply.mutateAsync({ id: "r1", reply_content: "Merci !" });
    });
    expect(post).toHaveBeenCalledWith("interactions/reviews/r1/reply/", { reply_content: "Merci !" });

    await act(async () => {
      await result.current.remove.mutateAsync("r1");
    });
    expect(del).toHaveBeenCalledWith("interactions/reviews/r1/");
    expect(client.getQueryData<Review[]>(reviewKeys.forPost("p1"))).toEqual([]);
  });
});

describe("useReportFakeContact", () => {
  afterEach(() => vi.restoreAllMocks());

  it("signale l'avis avec le motif CONTACT_FICTIF", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useReportFakeContact(), { wrapper: wrapperFor(newClient()) });
    await act(async () => {
      await result.current.mutateAsync({ reviewId: "r1", description: "Je ne connais pas cette personne." });
    });
    expect(post).toHaveBeenCalledWith("moderation/reports/", {
      target_type: "REVIEW",
      object_id: "r1",
      reason: "CONTACT_FICTIF",
      description: "Je ne connais pas cette personne.",
    });
  });
});
