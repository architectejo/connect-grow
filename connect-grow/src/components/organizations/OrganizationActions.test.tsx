import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { OrganizationInternal } from "@/api/types";
import identity from "@/api/__fixtures__/backend-identity.json";
import { ArchiveOrganizationCard, LeaveOrganizationCard } from "./OrganizationActions";

const leaveActive = vi.fn();
vi.mock("@/contexts/ActiveContextContext", () => ({ useActiveContext: () => ({ leaveActive }) }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const owner = identity.organization_internal_owner as unknown as OrganizationInternal;
const analyst = identity.organization_internal_analyst as unknown as OrganizationInternal;

const renderCard = (ui: React.ReactNode) =>
  render(
    <MemoryRouter initialEntries={["/organizations/x"]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
        <Routes>
          <Route path="/organizations/x" element={ui} />
          <Route path="/profiles" element={<p>Mes profils (page)</p>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  leaveActive.mockReset();
  online.value = true;
  vi.spyOn(apiClient, "get").mockResolvedValue({ data: { count: 0, next: null, previous: null, results: [] } });
});
afterEach(() => vi.restoreAllMocks());

describe("Quitter l'organisation (E4/E6)", () => {
  it("propose le départ à tous les rôles, avec confirmation dont le focus initial est « Annuler »", async () => {
    renderCard(<LeaveOrganizationCard org={analyst} />);
    fireEvent.click(screen.getByRole("button", { name: "Quitter l'organisation" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/Vous perdrez immédiatement l'accès/)).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Annuler" })).toHaveFocus());
  });

  it("succès (204) : retour au profil personnel avec l'alerte « left » si l'organisation était active, puis Mes profils", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ status: 204, data: "" });
    renderCard(<LeaveOrganizationCard org={analyst} />);
    fireEvent.click(screen.getByRole("button", { name: "Quitter l'organisation" }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Quitter l'organisation" }));
    expect(await screen.findByText("Mes profils (page)")).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith(`accounts/organizations/${analyst.id}/leave/`);
    expect(leaveActive).toHaveBeenCalledWith({ type: "ORGANIZATION", id: analyst.id }, "left");
  });

  it("dernier propriétaire (409 last_owner) : message persistant dans la page, aucune sortie du profil", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 409, data: { detail: "x", code: "last_owner" } } });
    renderCard(<LeaveOrganizationCard org={owner} />);
    fireEvent.click(screen.getByRole("button", { name: "Quitter l'organisation" }));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Quitter l'organisation" }));
    expect(await screen.findByText(/Vous êtes le dernier propriétaire : vous ne pouvez pas quitter l'organisation/)).toBeInTheDocument();
    expect(screen.queryByText("Mes profils (page)")).not.toBeInTheDocument();
    expect(leaveActive).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("déjà retiré (DENY_RELATION) : traité comme un départ, sans erreur", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "DENY_RELATION" } } });
    renderCard(<LeaveOrganizationCard org={analyst} />);
    fireEvent.click(screen.getByRole("button", { name: "Quitter l'organisation" }));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Quitter l'organisation" }));
    expect(await screen.findByText("Mes profils (page)")).toBeInTheDocument();
  });

  it("hors ligne : bouton désactivé, aucune sortie mise en file", () => {
    online.value = false;
    renderCard(<LeaveOrganizationCard org={analyst} />);
    expect(screen.getByRole("button", { name: "Quitter l'organisation" })).toBeDisabled();
    expect(screen.getByText("Reconnectez-vous pour effectuer cette action.")).toBeInTheDocument();
  });
});

describe("Archiver l'organisation (propriétaire)", () => {
  it("réservé aux détenteurs de org.archive : rien pour un administrateur ou un analyste", () => {
    const { container } = renderCard(<ArchiveOrganizationCard org={analyst} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("« Je comprends » obligatoire avant de pouvoir archiver", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { ...owner, status: "ARCHIVED" } });
    renderCard(<ArchiveOrganizationCard org={owner} />);
    fireEvent.click(screen.getByRole("button", { name: "Archiver l'organisation" }));
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Archiver l'organisation" });
    expect(confirm).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Je comprends" }));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(await screen.findByText("Mes profils (page)")).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith(`accounts/organizations/${owner.id}/archive/`);
    expect(leaveActive).toHaveBeenCalledWith({ type: "ORGANIZATION", id: owner.id }, "archived");
  });

  it("droit retiré entre-temps (DENY_PERMISSION) : message de rôle, la page reste", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "DENY_PERMISSION" } } });
    renderCard(<ArchiveOrganizationCard org={owner} />);
    fireEvent.click(screen.getByRole("button", { name: "Archiver l'organisation" }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Je comprends" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Archiver l'organisation" }));
    expect(await screen.findByText(/Votre rôle ne permet pas cette action/)).toBeInTheDocument();
    expect(leaveActive).not.toHaveBeenCalled();
  });
});
