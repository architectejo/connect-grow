import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import OrganizationNew from "./OrganizationNew";

const auth = vi.hoisted(() => ({ user: { id: "u1", full_name: "Compte Test", phone_verified: true } as Record<string, unknown>, isAuthenticated: true }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/components/layout/AccountShell", () => ({
  AccountShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const CITY = "11111111-1111-4111-8111-111111111111";
const COMMUNE = "22222222-2222-4222-8222-222222222222";
const CREATED = { id: "33333333-3333-4333-8333-333333333333", name: "Aide Kin", status: "ACTIVE" };

function Landing() {
  const location = useLocation();
  return <p data-testid="landing">{`${location.pathname}|${JSON.stringify(location.state)}`}</p>;
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/organizations/new"]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
        <Routes>
          <Route path="/organizations/new" element={<OrganizationNew />} />
          <Route path="/organizations/:id" element={<Landing />} />
          <Route path="/settings" element={<p>réglages</p>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  auth.user = { id: "u1", full_name: "Compte Test", phone_verified: true };
  online.value = true;
  vi.spyOn(apiClient, "get").mockImplementation((async (url: string) => {
    if (url.includes("limits")) {
      return { data: { max_categories_per_context: 5, max_organizations_per_account: 10, name_min_length: 2, name_max_length: 255, description_max_length: 2000 } };
    }
    if (url.includes("cities")) return { data: [{ id: CITY, name: "Kinshasa", communes: [{ id: COMMUNE, name: "Gombe", city: CITY }] }] };
    if (url.includes("categories")) return { data: [{ id: "44444444-4444-4444-8444-444444444444", name: "Mode", slug: "mode" }] };
    return { data: [] };
  }) as never);
});
afterEach(() => vi.restoreAllMocks());

const fillAndSubmit = async (name = "Aide Kin") => {
  fireEvent.click(await screen.findByRole("radio", { name: /ONG/ }));
  fireEvent.change(screen.getByLabelText("Nom de l'organisation"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "Créer l'organisation" }));
};

describe("OrganizationNew (E3)", () => {
  it("numéro de connexion non vérifié : message bloquant à la place du formulaire", async () => {
    auth.user = { id: "u1", full_name: "Compte Test", phone_verified: false };
    renderPage();
    expect(await screen.findByText("Vérifiez d'abord votre numéro de connexion")).toBeInTheDocument();
    expect(screen.queryByLabelText("Nom de l'organisation")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vérifier mon numéro" })).toHaveAttribute("href", "/settings?tab=contact");
  });

  it("champ phone_verified inconnu : le formulaire s'affiche (le serveur décidera)", async () => {
    auth.user = { id: "u1", full_name: "Compte Test" };
    renderPage();
    expect(await screen.findByLabelText("Nom de l'organisation")).toBeInTheDocument();
  });

  it("type et nom obligatoires : rien n'est envoyé tant que le formulaire est invalide", async () => {
    const post = vi.spyOn(apiClient, "post");
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Créer l'organisation" }));
    expect(await screen.findByText("Choisissez un type d'organisation.")).toBeInTheDocument();
    expect(screen.getByText(/Saisissez le nom de l'organisation/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("le type se choisit aux flèches (groupe radio à un seul arrêt de tabulation)", async () => {
    renderPage();
    const first = await screen.findByRole("radio", { name: /Entreprise/ });
    expect(first).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: /Boutique/ })).toHaveAttribute("aria-checked", "true");
  });

  it("création : corps JSON conforme, sans vendeur ni statut, puis aperçu de l'organisation SANS bascule automatique", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ status: 201, data: CREATED });
    renderPage();
    await fillAndSubmit();
    const landing = await screen.findByTestId("landing");
    expect(landing).toHaveTextContent(`/organizations/${CREATED.id}|{"justCreated":true}`);
    expect(post).toHaveBeenCalledTimes(1);
    const [url, body] = post.mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe("accounts/organizations/");
    expect(body).toEqual({ name: "Aide Kin", org_type: "ONG", description: "", nif: "", category_ids: [], city_id: null, commune_id: null });
    for (const key of ["seller", "status", "my_role", "id", "created_by"]) expect(body).not.toHaveProperty(key);
  });

  it("organization_limit_reached (409) : message du plafond et lien vers Mes profils, saisie conservée", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 409, data: { detail: "x", code: "organization_limit_reached" } } });
    renderPage();
    await fillAndSubmit();
    expect(await screen.findByText(/nombre maximal d'organisations pour un compte/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir mes profils" })).toHaveAttribute("href", "/profiles");
    expect(screen.getByLabelText("Nom de l'organisation")).toHaveValue("Aide Kin");
  });

  it("phone_verification_required (403) traité à l'envoi quand le champ est inconnu", async () => {
    auth.user = { id: "u1", full_name: "Compte Test" };
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "phone_verification_required" } } });
    renderPage();
    await fillAndSubmit();
    expect(await screen.findByText("Vérifiez d'abord votre numéro de téléphone de connexion pour créer une organisation.")).toBeInTheDocument();
  });

  it("compte restreint (DENY_SECURITY) : message de limitation", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "DENY_SECURITY" } } });
    renderPage();
    await fillAndSubmit();
    expect(await screen.findByText(/temporairement impossible/)).toBeInTheDocument();
  });

  it("erreur de champ du serveur (nom refusé) : affichée sous le champ", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 400, data: { name: ["Ce nom n'est pas valide."] } } });
    renderPage();
    await fillAndSubmit();
    expect(await screen.findByText("Ce nom n'est pas valide.")).toBeInTheDocument();
  });

  it("hors ligne : envoi désactivé, aucune création mise en file, saisie conservée", async () => {
    online.value = false;
    const post = vi.spyOn(apiClient, "post");
    renderPage();
    const submit = await screen.findByRole("button", { name: "Créer l'organisation" });
    expect(submit).toBeDisabled();
    expect(screen.getByText(/Reconnectez-vous pour effectuer cette action/)).toBeInTheDocument();
    fireEvent.click(submit);
    await waitFor(() => expect(post).not.toHaveBeenCalled());
  });

  it("pas de double envoi pendant la création", async () => {
    let resolve: (value: unknown) => void = () => undefined;
    const post = vi.spyOn(apiClient, "post").mockReturnValue(new Promise((r) => (resolve = r)) as never);
    renderPage();
    await fillAndSubmit();
    await waitFor(() => expect(screen.getByRole("button", { name: "Créer l'organisation" })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Créer l'organisation" }));
    expect(post).toHaveBeenCalledTimes(1);
    resolve({ status: 201, data: CREATED });
    await screen.findByTestId("landing");
  });
});
