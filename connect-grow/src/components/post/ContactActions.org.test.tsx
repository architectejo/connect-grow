import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import type { ContactChannel } from "@/api/types";
import { ContactActions } from "./ContactActions";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const OFFER = "11111111-1111-4111-8111-111111111111";

const renderActions = (allowed: ContactChannel[], sellerType: "ORGANIZATION" | "USER", layout: "stack" | "bar" = "stack", onMessage = vi.fn()) =>
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <ContactActions offerId={OFFER} sellerName="Atelier X" allowedChannels={allowed} sellerType={sellerType} layout={layout} onMessage={onMessage} />
      </QueryClientProvider>
    </MemoryRouter>,
  );

describe("contact d'une offre d'organisation", () => {
  it("canal Message seul : un seul bouton, jamais d'appel ni de WhatsApp grisé, et le texte explicatif", () => {
    const onMessage = vi.fn();
    renderActions(["MESSAGE"], "ORGANIZATION", "stack", onMessage);
    fireEvent.click(screen.getByRole("button", { name: /Envoyer un message/ }));
    expect(onMessage).toHaveBeenCalled();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /Appeler/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /WhatsApp/ })).not.toBeInTheDocument();
    expect(screen.getByText("Cette organisation se contacte par message dans Connecte+.")).toBeInTheDocument();
  });

  it("même texte dans la barre mobile", () => {
    renderActions(["MESSAGE"], "ORGANIZATION", "bar");
    expect(screen.getByText("Cette organisation se contacte par message dans Connecte+.")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("aucun canal (seller_contact_unavailable) : pas de bouton, message explicite, sans repli vers un autre moyen", () => {
    renderActions([], "ORGANIZATION");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText("Cette organisation ne peut pas être contactée pour le moment.")).toBeInTheDocument();
  });

  it("le client suit allowed_channels : si le serveur ouvre l'appel d'une organisation, le bouton apparaît et le texte « message seul » disparaît", () => {
    renderActions(["MESSAGE", "CALL"], "ORGANIZATION");
    expect(screen.getByRole("button", { name: /Appeler/ })).toBeInTheDocument();
    expect(screen.queryByText("Cette organisation se contacte par message dans Connecte+.")).not.toBeInTheDocument();
  });

  it("un vendeur particulier sans canal garde le texte historique", () => {
    renderActions([], "USER");
    expect(screen.getByText("Ce vendeur n'accepte aucun moyen de contact pour le moment.")).toBeInTheDocument();
  });
});
