import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import Dashboard from "./Dashboard";

const ORG = "22222222-2222-4222-8222-222222222222";
const MEMBER_CAPS = ["org.leave", "org.view_internal"];
const ANALYST_CAPS = ["offer.view_internal", "org.leave", "org.view_internal", "stats.view"];

const state = vi.hoisted(() => ({
  active: {} as { type: string; id: string; name: string; role: string | null; confirmed: boolean; capabilities: string[] },
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true, user: { full_name: "Rose Nzuzi" } }) }));
vi.mock("@/contexts/ActiveContextContext", () => ({
  useActiveContext: () => ({ active: state.active, contexts: [], unavailable: [] }),
  useCan: (capability: string) => state.active.capabilities.includes(capability),
}));
vi.mock("@/components/layout/AccountShell", () => ({ AccountShell: ({ children }: { children: ReactNode }) => <main>{children}</main> }));
vi.mock("@/hooks/use-organizations", () => ({ useOrganization: () => ({ data: undefined }) }));

const STATS = { summary: { total_views: 120, today_views: 4, active_posts: 2, review_count: 0, avg_rating: null }, history: [] };
const denied = { response: { status: 403, data: { detail: "Refus", code: "DENY_PERMISSION" }, headers: {} } };
const serverError = { response: { status: 500, data: {}, headers: {} } };

type Answer = { data: unknown } | { error: unknown };
const mockApi = (answers: { stats: Answer; posts: Answer }) =>
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    const answer = url.startsWith("marketplace/stats/dashboard") ? answers.stats : url.startsWith("marketplace/posts") ? answers.posts : { data: [] };
    if ("error" in answer) throw answer.error;
    return { data: answer.data };
  });

const renderPage = () =>
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  );

const requested = (get: ReturnType<typeof mockApi>, prefix: string) => get.mock.calls.some(([url]) => String(url).startsWith(prefix));

beforeAll(() => {
  // Le graphique des vues mesure son conteneur : jsdom n'a pas ResizeObserver
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});
beforeEach(() => {
  state.active = { type: "ORGANIZATION", id: ORG, name: "Atelier Kin", role: "ANALYST", confirmed: true, capabilities: ANALYST_CAPS };
});
afterEach(() => vi.restoreAllMocks());

describe("tableau de bord : rôle sans statistiques (MEMBER, contrat L1-01 §7.1)", () => {
  it("profil confirmé sans stats.view : état explicite avec sorties utiles, aucune requête vouée au refus", async () => {
    state.active = { ...state.active, role: "MEMBER", capabilities: MEMBER_CAPS };
    const get = mockApi({ stats: { data: STATS }, posts: { data: [] } });
    renderPage();
    expect(screen.getByRole("heading", { name: "Cette section n'est pas disponible pour votre rôle" })).toBeInTheDocument();
    expect(screen.getByText(/Avec le rôle Membre dans « Atelier Kin », vous voyez l'espace interne/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ouvrir l'espace de l'organisation" })).toHaveAttribute("href", `/organizations/${ORG}`);
    expect(screen.getByRole("link", { name: "Voir l'équipe" })).toHaveAttribute("href", `/organizations/${ORG}/team`);
    expect(screen.getByRole("link", { name: "Changer de profil" })).toHaveAttribute("href", "/profiles");
    // Ni tuiles muettes, ni « Mes annonces », ni bouton « Réessayer », ni publication
    expect(screen.queryByText("Vues totales")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Mes annonces" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Nouvelle annonce/ })).not.toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(requested(get, "marketplace/stats/dashboard")).toBe(false);
    expect(requested(get, "marketplace/posts")).toBe(false);
  });

  it("profil pas encore confirmé, refus 403 DENY_PERMISSION du serveur : même état explicite, sans « Réessayer »", async () => {
    state.active = { ...state.active, role: null, confirmed: false, capabilities: [] };
    const get = mockApi({ stats: { error: denied }, posts: { error: denied } });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Cette section n'est pas disponible pour votre rôle" })).toBeInTheDocument();
    expect(screen.getByText("Votre rôle ne donne pas accès aux statistiques ni aux offres de ce profil.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
    expect(requested(get, "marketplace/stats/dashboard")).toBe(true);
  });

  it("profil personnel sans organisation : pas de lien vers un espace d'organisation", async () => {
    state.active = { type: "USER", id: "u1", name: "Rose Nzuzi", role: null, confirmed: true, capabilities: [] };
    mockApi({ stats: { data: STATS }, posts: { data: [] } });
    renderPage();
    expect(screen.queryByRole("link", { name: "Ouvrir l'espace de l'organisation" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Changer de profil" })).toBeInTheDocument();
  });
});

describe("tableau de bord : erreurs gérées", () => {
  it("statistiques en erreur (500) : message et « Réessayer » qui relance la requête", async () => {
    const get = mockApi({ stats: { error: serverError }, posts: { data: [] } });
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Impossible de charger les statistiques.")).toBeInTheDocument();
    const calls = get.mock.calls.filter(([url]) => String(url).startsWith("marketplace/stats/dashboard")).length;
    fireEvent.click(within(alert).getByRole("button", { name: "Réessayer" }));
    await waitFor(() => expect(get.mock.calls.filter(([url]) => String(url).startsWith("marketplace/stats/dashboard")).length).toBe(calls + 1));
  });

  it("« Mes annonces » refusée (403 DENY_PERMISSION) : message clair à la place de « Réessayer »", async () => {
    mockApi({ stats: { data: STATS }, posts: { error: denied } });
    renderPage();
    expect(await screen.findByText("Votre rôle ne permet pas de voir les offres de ce profil.")).toBeInTheDocument();
    const section = screen.getByRole("heading", { name: "Mes annonces" }).closest("section") as HTMLElement;
    expect(within(section).queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
    expect(within(section).queryByText(/annonces? en ligne/)).not.toBeInTheDocument();
    // Les statistiques restent affichées
    expect(await screen.findByText("120")).toBeInTheDocument();
  });

  it("analyste : statistiques et annonces normales (non-régression)", async () => {
    mockApi({ stats: { data: STATS }, posts: { data: [] } });
    renderPage();
    expect(await screen.findByText("120")).toBeInTheDocument();
    expect(screen.getByText("Vues totales")).toBeInTheDocument();
    expect(screen.queryByText("Cette section n'est pas disponible pour votre rôle")).not.toBeInTheDocument();
  });
});
