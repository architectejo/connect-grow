import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import { ReceivedRevealsSection } from "./ReceivedRevealsSection";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const page = (results: unknown[], next: string | null = null) => ({ data: { count: results.length, next, previous: null, results } });
const row = (id: string, channel: "CALL" | "WHATSAPP", name = "Marie K.") => ({
  id,
  channel,
  created_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
  requester_display_name: name,
  offer: { id: "o1", title: "Chaussures" },
});

const renderSection = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  return render(<ReceivedRevealsSection />, { wrapper: Wrapper });
};

describe("ReceivedRevealsSection", () => {
  afterEach(() => vi.restoreAllMocks());

  it("affiche nom abrégé, canal, offre et date relative, sans numéro", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(page([row("a", "CALL"), row("b", "WHATSAPP", "Jean P.")]));
    const { container } = renderSection();
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Marie K. a demandé à vous contacter par Appel à propos de « Chaussures »");
    expect(items[0]).toHaveTextContent(/il y a 3 heures/);
    expect(items[1]).toHaveTextContent("Jean P.");
    expect(container.innerHTML).not.toMatch(/\+243|tel:|wa\.me/);
  });

  it("état de chargement puis état vide, avec lien vers les paramètres", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(page([]));
    renderSection();
    expect(screen.getByRole("status", { name: "Chargement des demandes…" })).toBeInTheDocument();
    expect(await screen.findByText("Personne n'a encore demandé votre numéro.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Paramètres" })).toHaveAttribute("href", "/settings");
  });

  it("erreur : Réessayer relance la requête", async () => {
    const get = vi.spyOn(apiClient, "get").mockRejectedValueOnce(new Error("Network Error")).mockResolvedValueOnce(page([row("a", "CALL")]));
    renderSection();
    expect(await screen.findByText("Impossible de charger les demandes de contact.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findAllByRole("listitem")).toHaveLength(1);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("le filtre par canal relit la liste avec ?channel=", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(page([row("a", "CALL")]));
    renderSection();
    await screen.findAllByRole("listitem");
    const group = screen.getByRole("group", { name: "Filtrer par moyen de contact" });
    expect(within(group).getByRole("button", { name: "Tous" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(within(group).getByRole("button", { name: "WhatsApp" }));
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith("interactions/contacts/reveals/received/", { params: { channel: "WHATSAPP", page: 1 } }),
    );
    expect(within(group).getByRole("button", { name: "WhatsApp" })).toHaveAttribute("aria-pressed", "true");
  });

  it("« Voir plus » charge la page suivante", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce(page([row("a", "CALL")], "http://x/?page=2"))
      .mockResolvedValueOnce(page([row("b", "CALL", "Paul T.")]));
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(screen.getByRole("button", { name: "Voir plus de demandes" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(get).toHaveBeenLastCalledWith("interactions/contacts/reveals/received/", { params: { page: 2 } });
    expect(screen.queryByRole("button", { name: "Voir plus de demandes" })).not.toBeInTheDocument();
  });
});
