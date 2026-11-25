import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import fixture from "@/api/__fixtures__/contexts.json";
import type { AvailableContext } from "@/api/types";
import { ActiveContextProvider, useActiveContext } from "@/contexts/ActiveContextContext";
import { activeContextStore, toSelection } from "@/lib/active-context";
import { AccessDenied } from "@/components/common/AccessDenied";
import { ActiveContextBanner } from "./ActiveContextBanner";
import { ContextLostAlert, ContextLostAlertHost } from "./ContextLostAlert";
import { ContextSwitcher } from "./ContextSwitcher";

const USER_ID = "11111111-1111-4111-8111-111111111111";
const auth = { user: { id: USER_ID, full_name: "Compte Test" }, isAuthenticated: true };
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

const all = fixture.response.results as AvailableContext[];
const shop = all[2];

let server: AvailableContext[];
let failing: boolean;

function Active() {
  const { active } = useActiveContext();
  return <p data-testid="active">{`${active.type}:${active.name}`}</p>;
}

const renderIn = (ui: ReactNode) =>
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ActiveContextProvider>
          {ui}
          <Active />
        </ActiveContextProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  localStorage.clear();
  activeContextStore._resetForTests();
  auth.isAuthenticated = true;
  server = all;
  failing = false;
  vi.spyOn(apiClient, "get").mockImplementation(async () => {
    if (failing) throw Object.assign(new Error("429"), { isAxiosError: true, response: { status: 429, data: {}, headers: {} } });
    return { data: { count: server.length, next: null, previous: null, results: server } };
  });
});
afterEach(() => vi.restoreAllMocks());

describe("ContextSwitcher (menu desktop)", () => {
  const openMenu = async () => {
    renderIn(<ContextSwitcher variant="pill" />);
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("USER:Compte Test"));
    await waitFor(() => expect(screen.getByRole("button", { name: /Profil actif : Compte Test/ })).toBeInTheDocument());
    const trigger = screen.getByRole("button", { name: /Profil actif/ });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });
    return screen.findByRole("menu");
  };

  it("s'ouvre au clavier et liste les profils en menuitemradio, le profil actif coché", async () => {
    const menu = await openMenu();
    const items = within(menu).getAllByRole("menuitemradio");
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveAttribute("aria-checked", "true");
    expect(items[2]).toHaveAttribute("aria-checked", "false");
    expect(items[2]).toHaveTextContent("Boutique Test");
    expect(items[2]).toHaveTextContent("Boutique"); // type de l'organisation
    expect(items[2]).toHaveTextContent("Administrateur"); // rôle
    expect(items[3]).toHaveTextContent("Analyste");
  });

  it("flèches puis Entrée choisissent un profil ; le menu se ferme", async () => {
    const menu = await openMenu();
    const items = within(menu).getAllByRole("menuitemradio");
    act(() => items[0].focus());
    // Les flèches sont traitées par l'élément qui a le focus (navigation Radix)
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowDown" });
    await waitFor(() => expect(items[1]).toHaveFocus());
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowDown" });
    await waitFor(() => expect(items[2]).toHaveFocus());
    fireEvent.keyDown(items[2], { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("ORGANIZATION:Boutique Test"));
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });

  it("Échap ferme le menu sans changer de profil", async () => {
    const menu = await openMenu();
    fireEvent.keyDown(menu, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    expect(screen.getByTestId("active")).toHaveTextContent("USER:Compte Test");
  });

  it("n'affiche aucun lien de gestion tant que les écrans n'existent pas (F2)", async () => {
    const menu = await openMenu();
    expect(within(menu).queryByText("Mes profils")).not.toBeInTheDocument();
  });

  it("affiche les liens « Mes profils » et « Créer une organisation » quand ils sont activés", async () => {
    renderIn(<ContextSwitcher variant="pill" showManagementLinks />);
    const trigger = await screen.findByRole("button", { name: /Profil actif : Compte Test/ });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("link", { name: "Mes profils" })).toHaveAttribute("href", "/profiles");
    expect(within(menu).getByRole("link", { name: "Créer une organisation" })).toHaveAttribute("href", "/organizations/new");
  });

  it("erreur de chargement : le profil mémorisé reste affiché et sélectionné, avec « Réessayer »", async () => {
    activeContextStore.set(toSelection(USER_ID, shop));
    failing = true;
    renderIn(<ContextSwitcher variant="pill" />);
    const trigger = await screen.findByRole("button", { name: /Profil actif : Boutique Test/ });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });
    const menu = await screen.findByRole("menu");
    await within(menu).findByText("Impossible de charger vos profils.");
    expect(within(menu).getByRole("menuitemradio", { name: /Boutique Test/ })).toHaveAttribute("aria-checked", "true");
    failing = false;
    fireEvent.click(within(menu).getByRole("button", { name: "Réessayer" }));
    await waitFor(() => expect(within(screen.getByRole("menu")).queryByText("Impossible de charger vos profils.")).not.toBeInTheDocument());
    expect(screen.getByTestId("active")).toHaveTextContent("ORGANIZATION:Boutique Test");
  });
});

describe("ContextSwitcher (feuille basse mobile)", () => {
  it("le bandeau ouvre un groupe radio ; choisir un profil le change et ferme la feuille", async () => {
    renderIn(<ContextSwitcher variant="banner" />);
    const banner = await screen.findByRole("button", { name: /Profil actif : Compte Test/ });
    expect(banner).toHaveTextContent("Profil personnel");
    fireEvent.click(banner);
    const group = await screen.findByRole("radiogroup", { name: "Agir en tant que" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(4);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    fireEvent.click(radios[3]);
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("ORGANIZATION:Collectif Test"));
    // La feuille se ferme (vaul garde le nœud le temps de son animation, absente de jsdom)
    await waitFor(() => expect(screen.queryByRole("dialog")?.getAttribute("data-state") ?? "closed").toBe("closed"));
  });

  it("chaque ligne est un bouton atteignable au clavier (Tab) d'au moins 48 px", async () => {
    renderIn(<ContextSwitcher variant="banner" />);
    fireEvent.click(await screen.findByRole("button", { name: /Profil actif/ }));
    const radios = within(await screen.findByRole("radiogroup")).getAllByRole("radio");
    for (const radio of radios) {
      expect(radio.tagName).toBe("BUTTON");
      expect(radio.className).toContain("min-h-12");
    }
  });
});

describe("ActiveContextBanner", () => {
  it("invisible pour un visiteur", () => {
    auth.isAuthenticated = false;
    renderIn(<ActiveContextBanner />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("organisation active : texte « au nom de » avec le rôle, et retour au personnel en un geste", async () => {
    activeContextStore.set(toSelection(USER_ID, shop));
    renderIn(<ActiveContextBanner />);
    const region = (await screen.findAllByRole("region", { name: "Profil actif" })).at(-1) as HTMLElement;
    expect(region).toHaveTextContent("Vous agissez au nom de Boutique Test · Administrateur");
    fireEvent.click(within(region).getByRole("button", { name: "Passer au profil personnel" }));
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("USER:Compte Test"));
    expect(localStorage.getItem("connecte.activeContext.v1")).toBeNull();
  });
});

describe("ContextLostAlert", () => {
  it("alerte persistante (role=alert), explique la cause, reçoit le focus et se ferme sur demande", () => {
    const onDismiss = vi.fn();
    render(<ContextLostAlert reason="RELATION" lostName="Boutique Test" onDismiss={onDismiss} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Votre profil actif a changé");
    expect(alert).toHaveTextContent("Vous ne faites plus partie de cette organisation. Vous agissez maintenant sous votre profil personnel.");
    expect(alert).toHaveTextContent("Boutique Test");
    expect(alert).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "J'ai compris" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["CONTEXT", "Le profil sélectionné n'est pas disponible."],
    ["SECURITY", "Votre profil n'est plus disponible pour le moment."],
    ["org_suspended", "Cette organisation est suspendue."],
    ["org_archived", "Cette organisation est archivée."],
    ["OBJECT_STATE", "Ce profil est archivé."],
    ["left", "Vous avez quitté l'organisation."],
    ["archived", "L'organisation est archivée."],
  ] as const)("raison %s", (reason, text) => {
    render(<ContextLostAlert reason={reason} lostName="" onDismiss={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent(text);
  });

  it("organisation perdue confirmée suspendue ou archivée : lien « Voir l'état de l'organisation » vers /organizations/:id", () => {
    render(
      <MemoryRouter>
        <ContextLostAlert reason="org_suspended" lostName="Atelier" lostId="55555555-5555-4555-8555-555555555555" onDismiss={() => {}} />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: "Voir l'état de l'organisation" });
    expect(link).toHaveAttribute("href", "/organizations/55555555-5555-4555-8555-555555555555");
    expect(screen.getByRole("alert")).toHaveFocus();
  });

  it("raison inconnue du serveur (compte limité) : pas de lien d'état", () => {
    render(
      <MemoryRouter>
        <ContextLostAlert reason="SECURITY" lostName="Atelier" lostId="55555555-5555-4555-8555-555555555555" onDismiss={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).not.toHaveTextContent("est suspendue");
  });

  it("l'hôte affiche la perte réelle et reste affiché tant qu'elle n'est pas fermée", async () => {
    activeContextStore.set(toSelection(USER_ID, shop));
    server = all.filter((c) => c.id !== shop.id);
    renderIn(<ContextLostAlertHost />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Le profil sélectionné n'est pas disponible.");
    expect(screen.getByTestId("active")).toHaveTextContent("USER:Compte Test");
    fireEvent.click(screen.getByRole("button", { name: "J'ai compris" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
});

describe("AccessDenied", () => {
  it("état « permission refusée » avec titre par défaut et action", () => {
    render(<AccessDenied description="Vous n'avez pas accès à cette organisation." action={<button type="button">Mes profils</button>} />);
    expect(screen.getByRole("heading", { name: "Accès refusé" })).toBeInTheDocument();
    expect(screen.getByText("Vous n'avez pas accès à cette organisation.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mes profils" })).toBeInTheDocument();
  });
});
