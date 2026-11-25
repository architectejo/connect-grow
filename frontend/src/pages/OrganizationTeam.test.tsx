import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

// Rendu jsdom + Radix + fenêtres chargées à la demande : 1 à 3 s par cas sur la machine de développement, davantage
// quand toute la suite tourne en parallèle. Délai explicite propre à ce fichier (ne dépend pas de vitest.config.ts).
vi.setConfig({ testTimeout: 20_000 });

beforeAll(async () => {
  configure({ asyncUtilTimeout: 5000 });
  // Le dialogue d'invitation est chargé à l'ouverture (React.lazy) : on réchauffe le module
  await Promise.all([
    import("@/components/team/InviteDialog"),
    import("@/components/team/ChangeRoleDialog"),
    import("@/components/team/TransferOwnershipDialog"),
    import("@/components/team/RemoveMemberDialog"),
    import("@/components/team/RevokeInvitationDialog"),
  ]);
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
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url.endsWith("/invitations/")) return { data: { count: 0, next: null, previous: null, results: [] } };
    if (url.endsWith("/limits/")) return { data: { invitation_ttl_days: 7 } };
    return {
    data: {
      count: 1,
      next: null,
      previous: null,
      results: [{ membership_id: "00000000-0000-4000-8000-000000000001", display_name: "Marie K.", role: org.my_role, joined_at: "2026-09-09T08:00:00Z", is_self: true, is_last_effective_owner: null }],
    },
    };
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

  it("propriétaire : bouton « Inviter une personne » et onglets Membres / Invitations", async () => {
    renderPage(owner);
    await screen.findByText("Marie K.");
    expect(screen.getByRole("button", { name: "Inviter une personne" })).toBeEnabled();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Membres", "Invitations"]);
    expect(screen.getByRole("tab", { name: "Membres" })).toHaveAttribute("aria-selected", "true");
  });

  it("analyste : lecture seule, ni onglets ni bouton d'invitation", async () => {
    renderPage(analyst);
    await screen.findByText("Marie K.");
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Inviter une personne" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Invitations/)).not.toBeInTheDocument();
  });

  it("la requête des invitations part à l'ouverture de l'onglet, pas au chargement de la page", async () => {
    renderPage(owner);
    await screen.findByText("Marie K.");
    const urls = () => vi.mocked(apiClient.get).mock.calls.map((c) => String(c[0]));
    expect(urls().some((u) => u.endsWith("/invitations/"))).toBe(false);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Invitations" }), { button: 0 });
    fireEvent.click(screen.getByRole("tab", { name: "Invitations" }));
    expect(await screen.findByText("Aucune invitation en attente.")).toBeInTheDocument();
    expect(urls().some((u) => u.endsWith("/invitations/"))).toBe(true);
  });

  it("créer un lien : fenêtre d'invitation, puis « Terminer » sélectionne l'onglet Invitations et le jeton disparaît", async () => {
    const TOKEN = "tok_ABC-123_secretsecretsecretsecretsecret00";
    renderPage(owner);
    vi.spyOn(apiClient, "post").mockResolvedValue({
      data: { invitation_id: "44444444-4444-4444-8444-444444444441", role: "EDITOR", status: "PENDING", label: "", created_at: "x", expires_at: "2026-11-16T08:00:00Z", link_token: TOKEN },
    });
    await screen.findByText("Marie K.");
    fireEvent.click(screen.getByRole("button", { name: "Inviter une personne" }));
    const dialog = await screen.findByRole("dialog", { name: "Inviter une personne" });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Éditeur/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Créer le lien" }));
    expect(await screen.findByLabelText("Lien d'invitation")).toHaveValue(`${window.location.origin}/organization-invitation#token=${TOKEN}`);
    fireEvent.click(screen.getByRole("button", { name: "Terminer" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "Invitations" })).toHaveAttribute("aria-selected", "true");
    expect(document.body.innerHTML).not.toContain(TOKEN);
    expect(JSON.stringify({ ...sessionStorage, ...localStorage })).not.toContain(TOKEN);
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
    expect(urls.some((u) => u.endsWith("/invitations/"))).toBe(false);
  });

  it("onglets : cibles de 44 px", async () => {
    renderPage(owner);
    await screen.findByText("Marie K.");
    for (const tab of screen.getAllByRole("tab")) expect(tab.className).toContain("min-h-11");
  });

  it("fenêtre ouverte depuis l'état vide de l'onglet Invitations : le focus revient à ce bouton à l'annulation", async () => {
    renderPage(owner);
    await screen.findByText("Marie K.");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Invitations" }), { button: 0 });
    fireEvent.click(screen.getByRole("tab", { name: "Invitations" }));
    await screen.findByText("Aucune invitation en attente.");
    const panel = screen.getByRole("tabpanel");
    const emptyAction = within(panel).getByRole("button", { name: "Inviter une personne" });
    // Comme sous Safari, le clic ne donne pas le focus au bouton : le déclencheur doit être transmis explicitement
    expect(document.activeElement).not.toBe(emptyAction);
    fireEvent.click(emptyAction);
    const dialog = await screen.findByRole("dialog", { name: "Inviter une personne" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(emptyAction).toHaveFocus());
  });

  it("bouton d'en-tête cliqué sans prendre le focus : le focus lui revient à l'annulation", async () => {
    renderPage(owner);
    await screen.findByText("Marie K.");
    const header = screen.getByRole("button", { name: "Inviter une personne" });
    (document.activeElement as HTMLElement | null)?.blur();
    fireEvent.click(header);
    const dialog = await screen.findByRole("dialog", { name: "Inviter une personne" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(header).toHaveFocus());
  });
});
