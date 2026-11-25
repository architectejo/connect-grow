import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import identity from "@/api/__fixtures__/backend-identity.json";
import Messages from "./Messages";

// jsdom n'a pas ResizeObserver (utilisé par le composant de défilement)
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};

vi.mock("@/components/landing/Navbar", () => ({ default: () => null }));
vi.mock("@/components/layout/AppShell", () => ({ AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/layout/AccountShell", () => ({ RequireAuth: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const ORG_ID = identity.conversations_buyer[0].seller_context.id;
const personal = { type: "USER", id: "u1", name: "Marie Kabongo", role: null, capabilities: ["message.reply"], confirmed: true };
const organization = (capabilities: string[]) => ({ type: "ORGANIZATION", id: ORG_ID, name: "Atelier X", role: "OWNER", capabilities, confirmed: true });
const activeMock = vi.hoisted(() => ({ active: null as unknown }));
vi.mock("@/contexts/ActiveContextContext", () => ({ useActiveContext: () => ({ active: activeMock.active }) }));

const toast = await import("sonner").then((m) => m.toast);
const httpError = (status: number, data: unknown) => ({ response: { status, data, headers: {} } });

const renderPage = () =>
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Messages />
      </QueryClientProvider>
    </MemoryRouter>,
  );

describe("Messages : boîte selon le profil actif (T7)", () => {
  beforeEach(() => {
    activeMock.active = personal;
  });
  afterEach(() => vi.restoreAllMocks());

  const mockApi = (conversations: unknown, thread: unknown) =>
    vi.spyOn(apiClient, "get").mockImplementation((async (url: string) => {
      if (url === "interactions/conversations/") return { data: conversations };
      if (url === "interactions/messages/") return { data: thread };
      return { data: [] };
    }) as never);

  it("acheteur : voit l'organisation (jamais un membre), le badge « Organisation » et les messages de l'équipe sous le nom de l'organisation", async () => {
    mockApi(identity.conversations_buyer, identity.messages_buyer);
    renderPage();
    const row = await screen.findByRole("button", { name: /Atelier X/ });
    expect(within(row).getByTestId("conversation-badge")).toHaveTextContent("Organisation");
    fireEvent.click(row);
    const sender = await screen.findByTestId("message-sender");
    expect(sender).toHaveTextContent("Atelier X");
    expect(document.body.textContent).not.toMatch(/Nom owner|owner@example/);
  });

  it("organisation active : boîte de l'organisation, badge « Au nom de », acheteur abrégé", async () => {
    activeMock.active = organization(["message.reply"]);
    const get = mockApi(identity.conversations_organization, identity.messages_organization);
    renderPage();
    const row = await screen.findByRole("button", { name: /Marie K\./ });
    expect(within(row).getByTestId("conversation-badge")).toHaveTextContent("Au nom de Atelier X");
    expect(screen.getByText("Boîte de messages de Atelier X")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("interactions/conversations/");
  });

  it("rôle sans message.reply : accès refusé, aucune requête de conversations", async () => {
    activeMock.active = organization(["offer.view_internal"]);
    const get = mockApi([], []);
    renderPage();
    expect(await screen.findByText(/réservés au propriétaire et aux administrateurs/)).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it("boîte d'une organisation suspendue : message de refus clair et « Réessayer »", async () => {
    activeMock.active = organization(["message.reply"]);
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(403, identity.conversations_suspended_organization_error.body));
    renderPage();
    expect(await screen.findByText(/Votre compte est limité pour le moment/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("erreur sur la liste : texte français et « Réessayer »", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(400, {}));
    renderPage();
    expect(await screen.findByText("Impossible de charger vos conversations.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("aucune conversation : état vide", async () => {
    mockApi([], []);
    renderPage();
    expect(await screen.findByText("Aucune conversation")).toBeInTheDocument();
  });

  it("envoi refusé (organisation suspendue, DENY_SECURITY) : message français, le texte saisi est conservé", async () => {
    mockApi(identity.conversations_buyer, identity.messages_buyer);
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(403, identity.message_post_buyer_to_suspended_organization_error.body));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Atelier X/ }));
    const input = await screen.findByLabelText("Votre message");
    fireEvent.change(input, { target: { value: "Bonjour" } });
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("temporairement impossible")));
    expect(input).toHaveValue("Bonjour");
  });

  it("conversation devenue introuvable à l'envoi : retour à la liste rechargée", async () => {
    const get = mockApi(identity.conversations_buyer, identity.messages_buyer);
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(400, identity.message_post_unknown_conversation_error.body));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Atelier X/ }));
    fireEvent.change(await screen.findByLabelText("Votre message"), { target: { value: "Bonjour" } });
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Cette conversation n'est plus disponible. La liste a été mise à jour."));
    await waitFor(() => expect(get.mock.calls.filter(([url]) => url === "interactions/conversations/").length).toBeGreaterThan(1));
  });

  it("recherche locale : filtre les conversations", async () => {
    mockApi(identity.conversations_buyer, []);
    renderPage();
    await screen.findByRole("button", { name: /Atelier X/ });
    fireEvent.change(screen.getByLabelText("Rechercher une conversation"), { target: { value: "zzz" } });
    expect(screen.getByText("Aucune conversation ne correspond à votre recherche.")).toBeInTheDocument();
  });
});
