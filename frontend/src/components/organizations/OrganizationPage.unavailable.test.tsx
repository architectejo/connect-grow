import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import fixture from "@/api/__fixtures__/contexts.json";
import { ActiveContextProvider } from "@/contexts/ActiveContextContext";
import { UnavailableOrganizationsSection } from "@/components/profiles/UnavailableOrganizationsSection";
import { activeContextStore } from "@/lib/active-context";
import { OrganizationPage } from "./OrganizationPage";

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "11111111-1111-4111-8111-111111111111", full_name: "Compte Test" }, isAuthenticated: true }),
}));
vi.mock("@/components/layout/AccountShell", () => ({ AccountShell: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const [suspended, archived] = fixture.response.unavailable;
const OTHER_ID = "99999999-9999-4999-8999-999999999999";

let contextsBody: Record<string, unknown>;
let contextsCalls: number;
let internalCalls: string[];
let internalError: { status: number; code: string } | null;
let contextsFail: boolean;

const denied = (status: number, code: string) => ({ response: { status, data: { detail: "x", code }, headers: {} } });

beforeEach(() => {
  localStorage.clear();
  activeContextStore._resetForTests();
  online.value = true;
  contextsFail = false;
  contextsCalls = 0;
  internalCalls = [];
  internalError = null;
  contextsBody = { count: 1, next: null, previous: null, results: [fixture.response.results[0]], unavailable: [suspended, archived] };
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url === "accounts/contexts/") {
      contextsCalls++;
      if (contextsFail) throw denied(429, "throttled");
      return { data: contextsBody };
    }
    internalCalls.push(url);
    if (internalError) throw denied(internalError.status, internalError.code);
    return { data: {} };
  });
});
afterEach(() => vi.restoreAllMocks());

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ActiveContextProvider>
          <Routes>
            <Route path="/organizations/:id" element={<OrganizationPage section="overview">{() => <p>Contenu normal</p>}</OrganizationPage>} />
            <Route path="/profiles" element={<UnavailableOrganizationsSection />} />
          </Routes>
        </ActiveContextProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );

describe("OrganizationPage : organisation suspendue ou archivée", () => {
  it("affiche la vue d'état, sans interroger internal/ ni afficher « accès refusé »", async () => {
    renderAt(`/organizations/${suspended.id}`);
    expect(await screen.findByText("Cette organisation est suspendue")).toBeInTheDocument();
    expect(screen.queryByText("Contenu normal")).not.toBeInTheDocument();
    expect(screen.queryByText(/accès refusé|n.avez pas accès/i)).not.toBeInTheDocument();
    expect(internalCalls).toEqual([]);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("organisation archivée : texte « archivée » et recours de l'équipe", async () => {
    renderAt(`/organizations/${archived.id}`);
    expect(await screen.findByText("Cette organisation est archivée")).toBeInTheDocument();
    expect(screen.getByText(/Pour toute question, adressez-vous à un administrateur principal/)).toBeInTheDocument();
  });

  it("relit contexts/ une seule fois à l'ouverture (en ligne)", async () => {
    renderAt(`/organizations/${suspended.id}`);
    await screen.findByText("Cette organisation est suspendue");
    await waitFor(() => expect(contextsCalls).toBe(2));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(contextsCalls).toBe(2);
  });

  it("hors ligne : pas de relecture, « Quitter » désactivé", async () => {
    online.value = false;
    renderAt(`/organizations/${suspended.id}`);
    await screen.findByText("Cette organisation est suspendue");
    expect(contextsCalls).toBe(1);
    expect(screen.getByRole("button", { name: "Quitter l'organisation" })).toBeDisabled();
  });

  it("DENY_SECURITY sans entrée dans unavailable : compte limité, jamais « suspendue »", async () => {
    internalError = { status: 403, code: "DENY_SECURITY" };
    renderAt(`/organizations/${OTHER_ID}`);
    expect(await screen.findByText(/Votre compte est limité pour le moment/)).toBeInTheDocument();
    expect(screen.queryByText(/suspendue/i)).not.toBeInTheDocument();
  });

  it("DENY_RELATION : texte inchangé (non-membre)", async () => {
    internalError = { status: 403, code: "DENY_RELATION" };
    renderAt(`/organizations/${OTHER_ID}`);
    expect(await screen.findByText("Vous n'avez pas accès à cette organisation.")).toBeInTheDocument();
  });

  it("contexts/ en erreur et refus d'état : « Réessayer » plutôt qu'une hypothèse", async () => {
    contextsFail = true;
    internalError = { status: 403, code: "DENY_SECURITY" };
    renderAt(`/organizations/${OTHER_ID}`);
    expect(await screen.findByRole("button", { name: /Réessayer/ })).toBeInTheDocument();
    expect(screen.queryByText(/Votre compte est limité/)).not.toBeInTheDocument();
  });
});

describe("UnavailableOrganizationsSection (/profiles)", () => {
  it("liste les organisations avec badge de statut texte et rôle, sans « Agir sous ce profil »", async () => {
    renderAt("/profiles");
    expect(await screen.findByRole("heading", { name: "Organisations indisponibles" })).toBeInTheDocument();
    expect(screen.getByText("Vous ne pouvez plus agir au nom de ces organisations.")).toBeInTheDocument();
    expect(screen.getByText("Atelier Suspendu")).toBeInTheDocument();
    expect(screen.getByLabelText("Statut de l'organisation : Suspendue")).toBeInTheDocument();
    expect(screen.getByLabelText("Statut de l'organisation : Archivée")).toBeInTheDocument();
    expect(screen.getByText("Administrateur principal")).toBeInTheDocument();
    expect(screen.queryByText("Agir sous ce profil")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir l'état de Atelier Suspendu" })).toHaveAttribute("href", `/organizations/${suspended.id}`);
    expect(screen.getByRole("link", { name: "Voir l'état de Association Archivee" })).toBeInTheDocument();
  });

  it("section absente quand unavailable est vide ou absent", async () => {
    contextsBody = { ...contextsBody, unavailable: [] };
    const { unmount } = renderAt("/profiles");
    await waitFor(() => expect(contextsCalls).toBe(1));
    expect(screen.queryByRole("heading", { name: "Organisations indisponibles" })).not.toBeInTheDocument();
    unmount();
    delete contextsBody.unavailable;
    renderAt("/profiles");
    await waitFor(() => expect(contextsCalls).toBe(2));
    expect(screen.queryByRole("heading", { name: "Organisations indisponibles" })).not.toBeInTheDocument();
  });

  it("aucune requête de plus : une seule lecture de contexts/ au chargement", async () => {
    renderAt("/profiles");
    await screen.findByText("Atelier Suspendu");
    expect(contextsCalls).toBe(1);
  });
});
