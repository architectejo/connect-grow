import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import identity from "@/api/__fixtures__/backend-identity.json";
import Notifications from "./Notifications";

vi.mock("@/components/layout/AccountShell", () => ({ AccountShell: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@/hooks/use-features", () => ({ useFeatures: () => ({ exchangeEnabled: false }) }));

const renderPage = () =>
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Notifications />
      </QueryClientProvider>
    </MemoryRouter>,
  );

describe("Notifications : profils concernés (T6)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("affiche le profil de l'équipe et filtre par profil", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: identity.notifications_list });
    renderPage();
    expect(await screen.findByText("Nouveau message")).toBeInTheDocument();
    expect(screen.getByTestId("notification-context")).toHaveTextContent("Organisation Atelier X");
    expect(screen.getByText("Bienvenue")).toBeInTheDocument();

    const filter = screen.getByLabelText("Filtrer par profil");
    fireEvent.change(filter, { target: { value: (filter as HTMLSelectElement).options[2].value } });
    expect(screen.getByText("Nouveau message")).toBeInTheDocument();
    expect(screen.queryByText("Bienvenue")).not.toBeInTheDocument();

    fireEvent.change(filter, { target: { value: "personal" } });
    expect(screen.queryByText("Nouveau message")).not.toBeInTheDocument();
    expect(screen.getByText("Bienvenue")).toBeInTheDocument();
  });

  it("sans notification d'équipe, le filtre par profil n'est pas proposé", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [identity.notifications_list.find((n) => !n.context)] });
    renderPage();
    await screen.findByText("Bienvenue");
    expect(screen.queryByLabelText("Filtrer par profil")).not.toBeInTheDocument();
  });

  it("liste vide : état vide", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByText("Aucune notification")).toBeInTheDocument();
  });

  it("erreur serveur : bouton « Réessayer »", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({ response: { status: 500, data: {} } });
    renderPage();
    expect(await screen.findByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });
});
