import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { Post } from "@/api/types";
import { PostCard } from "@/components/common/PostCard";
import { ActiveFilters } from "@/components/marketplace/ActiveFilters";
import { FiltersPanel } from "@/components/marketplace/FiltersPanel";
import { usePostFilters } from "@/components/marketplace/use-post-filters";
import { featuresKeys } from "@/hooks/use-features";
import { usePosts } from "@/hooks/use-marketplace";
import { ExchangeDialog } from "./ContactDialogs";
import fixtures from "@/api/__fixtures__/backend-lot0.json";

const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { error: toastError, success: vi.fn() } }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const asPost = (value: unknown) => value as Post;
const postOff = asPost(fixtures.post_detail_exchange_off);
const postOn = asPost(fixtures.post_detail_exchange_on);
const OTHER_POST = { ...postOn, id: "33333333-3333-4333-8333-333333333333", title: "Autre annonce du même vendeur" } as Post;

let exchangeEnabled = false;
let featuresFails = false;
const get = vi.fn();

beforeEach(() => {
  exchangeEnabled = false;
  featuresFails = false;
  get.mockReset();
  toastError.mockReset();
  vi.spyOn(apiClient, "get").mockImplementation((async (url: string, config?: unknown) => {
    get(url, config);
    if (url.endsWith("config/features/")) {
      if (featuresFails) throw Object.assign(new Error("panne"), { response: { status: 503 } });
      return { data: { features: { exchange_enabled: exchangeEnabled } } };
    }
    if (url === "marketplace/posts/") return { data: { results: [postOn, OTHER_POST] } };
    return { data: [] };
  }) as never);
});
afterEach(() => vi.restoreAllMocks());

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function wrapperAt(url: string, client = newClient()) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[url]}>
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </MemoryRouter>
    );
  };
}

const renderIn = (ui: ReactNode, url = "/") => render(ui, { wrapper: wrapperAt(url) });
const featuresRequested = () => waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringContaining("config/features/"), undefined));
const settle = () => new Promise((resolve) => setTimeout(resolve, 30));

describe("filtre échangeable", () => {
  it("troc éteint : le paramètre de l'URL est ignoré et rien de troc n'est visible", async () => {
    const { result } = renderHook(() => usePostFilters(), { wrapper: wrapperAt("/marketplace?is_exchangeable=true&category=abc") });
    await featuresRequested();
    await settle();
    expect(result.current.filters).toEqual({ category: "abc" });
    expect(result.current.activeCount).toBe(1);

    renderIn(
      <>
        <FiltersPanel filters={{ is_exchangeable: "true" }} onChange={vi.fn()} />
        <ActiveFilters filters={{ is_exchangeable: "true" }} onChange={vi.fn()} onReset={vi.fn()} />
      </>,
    );
    await settle();
    expect(screen.queryByLabelText(/échangeable/i)).toBeNull();
    expect(screen.queryByText(/troc/i)).toBeNull();
    expect(screen.queryByText("Échangeable")).toBeNull();
  });

  it("troc éteint : la requête de liste n'envoie pas is_exchangeable", async () => {
    const { result: filters } = renderHook(() => usePostFilters(), { wrapper: wrapperAt("/marketplace?is_exchangeable=true") });
    await settle();
    const { result } = renderHook(() => usePosts(filters.current.filters), { wrapper: wrapperAt("/marketplace") });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const postsCall = get.mock.calls.find(([url]) => url === "marketplace/posts/");
    expect(postsCall?.[1]).toEqual({ params: {} });
  });

  it("troc allumé : interrupteur, pastille et paramètre sont présents", async () => {
    exchangeEnabled = true;
    const client = newClient();
    const { result } = renderHook(() => usePostFilters(), { wrapper: wrapperAt("/marketplace?is_exchangeable=true", client) });
    await waitFor(() => expect(result.current.filters.is_exchangeable).toBe("true"));
    expect(result.current.activeCount).toBe(1);

    render(
      <>
        <FiltersPanel filters={{ is_exchangeable: "true" }} onChange={vi.fn()} />
        <ActiveFilters filters={{ is_exchangeable: "true" }} onChange={vi.fn()} onReset={vi.fn()} />
      </>,
      { wrapper: wrapperAt("/", client) },
    );
    expect(await screen.findByText("Échangeable uniquement")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Retirer le filtre Échangeable/ })).toBeTruthy();
  });

  it("échec de la configuration : troc éteint", async () => {
    featuresFails = true;
    const { result } = renderHook(() => usePostFilters(), { wrapper: wrapperAt("/marketplace?is_exchangeable=true") });
    await featuresRequested();
    await settle();
    expect(result.current.filters.is_exchangeable).toBeUndefined();
  });
});

describe("badge « Échangeable » de la carte", () => {
  it("jamais affiché troc éteint, même si une ancienne réponse gardée hors ligne porte le champ", async () => {
    renderIn(<PostCard post={postOn} />);
    await featuresRequested();
    await settle();
    expect(screen.queryByText("Échangeable")).toBeNull();
    renderIn(<PostCard post={postOff} />);
    expect(screen.queryByText("Échangeable")).toBeNull();
  });

  it("affiché troc allumé quand l'annonce est échangeable", async () => {
    exchangeEnabled = true;
    renderIn(<PostCard post={postOn} />);
    expect(await screen.findByText("Échangeable")).toBeTruthy();
  });
});

describe("ExchangeDialog et feature_disabled (403)", () => {
  it("message français dédié, une seule tentative, dialogue refermé et configuration relue", async () => {
    exchangeEnabled = true;
    const post = vi.spyOn(apiClient, "post").mockRejectedValue(
      Object.assign(new Error("403"), {
        response: { status: 403, data: { detail: "Cette fonctionnalité n'est pas disponible.", code: "feature_disabled" } },
      }),
    );
    const client = newClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const onOpenChange = vi.fn();
    render(<ExchangeDialog post={postOn} open onOpenChange={onOpenChange} />, { wrapper: wrapperAt("/", client) });

    fireEvent.click(await screen.findByText(OTHER_POST.title));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Je propose cet échange." } });
    fireEvent.click(screen.getByRole("button", { name: /envoyer/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Le troc n'est pas disponible pour le moment."));
    expect(post).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: featuresKeys.all });
  });
});
