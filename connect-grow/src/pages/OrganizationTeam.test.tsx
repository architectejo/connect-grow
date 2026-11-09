import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { OrganizationInternal } from "@/api/types";
import identity from "@/api/__fixtures__/backend-identity.json";
import OrganizationTeam from "./OrganizationTeam";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => true }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
const current = vi.hoisted(() => ({ org: null as unknown }));
vi.mock("@/components/organizations/OrganizationPage", () => ({
  OrganizationPage: ({ children }: { children: (org: unknown) => ReactNode }) => <div>{children(current.org)}</div>,
}));
vi.mock("@/contexts/ActiveContextContext", () => ({ useActiveContext: () => ({ leaveActive: vi.fn(), switchToPersonal: vi.fn(), active: { type: "USER", id: "u" } }) }));

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});
afterEach(() => vi.restoreAllMocks());

const owner = identity.organization_internal_owner as unknown as OrganizationInternal;
const analyst = identity.organization_internal_analyst as unknown as OrganizationInternal;

const renderPage = (org: OrganizationInternal) => {
  current.org = org;
  vi.spyOn(apiClient, "get").mockResolvedValue({
    data: {
      count: 1,
      next: null,
      previous: null,
      results: [{ membership_id: "00000000-0000-4000-8000-000000000001", display_name: "Marie K.", role: org.my_role, joined_at: "2026-09-09T08:00:00Z", is_self: true, is_last_effective_owner: null }],
    },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <OrganizationTeam />
      </QueryClientProvider>
    </MemoryRouter>,
  );
};

describe("écran Équipe", () => {
  it("affiche la liste, mon rôle, la carte « Quitter l'organisation » et le tableau des rôles replié", async () => {
    renderPage(owner);
    expect(await screen.findByText("Marie K.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Équipe" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Votre rôle" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Quitter l'organisation" }).length).toBeGreaterThan(0);
    const rolesToggle = screen.getByRole("button", { name: "Que peut faire chaque rôle ?" });
    expect(rolesToggle).toHaveAttribute("aria-expanded", "false");
  });

  it("l'onglet Invitations et le bouton « Inviter une personne » ne sont pas montrés dans cette tâche (F2)", async () => {
    renderPage(owner);
    await screen.findByText("Marie K.");
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByText(/Invit/)).not.toBeInTheDocument();
  });

  it("région d'annonce unique aria-live=polite, vide au départ ; aucune requête d'invitations", async () => {
    renderPage(analyst);
    await screen.findByText("Marie K.");
    const live = screen.getAllByRole("status");
    expect(live).toHaveLength(1);
    expect(live[0]).toHaveAttribute("aria-live", "polite");
    expect(within(live[0]).queryByText(/./)).not.toBeInTheDocument();
    const urls = vi.mocked(apiClient.get).mock.calls.map((c) => String(c[0]));
    expect(urls.every((u) => u.endsWith("/members/"))).toBe(true);
  });
});
