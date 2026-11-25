import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { configure, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { SellerProfileData } from "@/api/types";
import identity from "@/api/__fixtures__/backend-identity.json";
import SellerProfile from "./SellerProfile";

vi.mock("@/components/layout/AppShell", () => ({ AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
const auth = vi.hoisted(() => ({ user: { id: "u1" } as { id: string } | null }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: auth.user, isAuthenticated: !!auth.user }) }));
const ctx = vi.hoisted(() => ({ contexts: [] as { type: string; id: string }[] }));
vi.mock("@/contexts/ActiveContextContext", () => ({ useActiveContext: () => ({ contexts: ctx.contexts }) }));
vi.mock("@/hooks/use-features", () => ({ useFeatures: () => ({ exchangeEnabled: false }) }));

const orgPost = identity.post_detail_organization;
const ORG_ID = orgPost.seller.context_id;

// Forme de GET marketplace/sellers/<type>/<id>/ (ADR 0006 §9.7), livrée par T5b : simulée ici
const orgProfile: SellerProfileData = {
  context_type: "ORGANIZATION",
  context_id: ORG_ID,
  display_name: orgPost.seller.display_name,
  photo: null,
  description: "Atelier de couture de Gombe",
  org_type: "ENTREPRISE",
  verified_claims: orgPost.seller.verified_claims,
  verification_summary: { complete: false, label: null },
  member_since: orgPost.seller.member_since,
  seller_rating: { average: null, count: 0 },
  active_offers_count: 1,
};

let profileError: unknown;
let profileData: SellerProfileData = orgProfile;
const get = vi.fn();

beforeEach(() => {
  auth.user = { id: "u1" };
  ctx.contexts = [];
  profileError = undefined;
  profileData = orgProfile;
  get.mockReset();
  vi.spyOn(apiClient, "get").mockImplementation((async (url: string, config?: unknown) => {
    get(url, config);
    if (url.startsWith("marketplace/sellers/")) {
      if (profileError) throw profileError;
      return { data: profileData };
    }
    if (url === "marketplace/posts/") return { data: [orgPost] };
    return { data: [] };
  }) as never);
});
afterEach(() => vi.restoreAllMocks());

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Routes>
          <Route path="/seller/:contextType/:id" element={<SellerProfile />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );

// Premier rendu jsdom (transformations à froid, Radix, i18n) : il dépasse les 5 s par défaut quand toute la suite tourne
// en parallèle sur la machine de développement. Délai explicite propre à ce fichier (ne dépend pas de vitest.config.ts).
vi.setConfig({ testTimeout: 20_000 });

beforeAll(() => {
  configure({ asyncUtilTimeout: 5000 });
});

describe("Profil public d'un vendeur (E9)", () => {
  it("organisation : nom, type, mentions précises, présentation, compteur d'offres et offres du vendeur", async () => {
    renderAt(`/seller/organization/${ORG_ID}`);
    expect(await screen.findByRole("heading", { level: 1, name: "Atelier Test" })).toBeInTheDocument();
    expect(screen.getByText("Organisation · Entreprise")).toBeInTheDocument();
    expect(screen.getByText("RCCM vérifié")).toBeInTheDocument();
    expect(screen.getByText("Atelier de couture de Gombe")).toBeInTheDocument();
    expect(screen.getByText("1 offre active")).toBeInTheDocument();
    expect(await screen.findByText("Costume sur mesure")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(`marketplace/sellers/organization/${ORG_ID}/`, undefined);
    expect(get).toHaveBeenCalledWith("marketplace/posts/", { params: { seller: ORG_ID, seller_type: "ORGANIZATION", ordering: "-created_at" } });
  });

  it("réponse réelle enregistrée du backend (T5b) : affichée sans coordonnée ni mention inventée", async () => {
    const real = identity.seller_profile_organization as unknown as SellerProfileData;
    profileData = real;
    const { container } = renderAt(`/seller/organization/${real.context_id}`);
    expect(await screen.findByRole("heading", { level: 1, name: real.display_name })).toBeInTheDocument();
    expect(screen.getByText("1 offre active")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\+243|@|score de confiance/i);
  });

  it("aucune coordonnée, aucun bouton de contact, aucun score de confiance", async () => {
    const { container } = renderAt(`/seller/organization/${ORG_ID}`);
    await screen.findByRole("heading", { level: 1 });
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\+243|@|tel:|wa\.me/);
    expect(text).not.toMatch(/score de confiance|trust/i);
    expect(screen.queryByRole("button", { name: /Appeler|WhatsApp|Contacter|Envoyer un message/ })).not.toBeInTheDocument();
  });

  it("vendeur introuvable (404) : message dédié et lien vers la marketplace", async () => {
    profileError = { response: { status: 404, data: { detail: "x", code: "not_found" } } };
    renderAt(`/seller/provider/${ORG_ID}`);
    expect(await screen.findByText("Ce vendeur n'existe pas ou n'est plus visible.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir le marketplace" })).toHaveAttribute("href", "/marketplace");
  });

  it("404 de sellers/user/<id>/ (utilisateur sans offre active) : état « introuvable », pas une erreur réseau", async () => {
    profileError = { response: { status: 404, data: identity.seller_profile_not_found_error.body } };
    renderAt(`/seller/user/${ORG_ID}`);
    expect(await screen.findByText("Ce vendeur n'existe pas ou n'est plus visible.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
  });

  it("type inconnu dans l'adresse : même message, aucune requête", () => {
    renderAt(`/seller/inconnu/${ORG_ID}`);
    expect(screen.getByText("Ce vendeur n'existe pas ou n'est plus visible.")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it("erreur serveur : « Réessayer »", async () => {
    profileError = { response: { status: 500, data: {} } };
    renderAt(`/seller/organization/${ORG_ID}`);
    expect(await screen.findByRole("button", { name: "Réessayer" }, { timeout: 5000 })).toBeInTheDocument();
  });

  it("membre de l'organisation : lien de modification vers son espace", async () => {
    ctx.contexts = [{ type: "ORGANIZATION", id: ORG_ID }];
    renderAt(`/seller/organization/${ORG_ID}`);
    expect(await screen.findByRole("link", { name: "Modifier mon profil" })).toHaveAttribute("href", `/organizations/${ORG_ID}/edit`);
  });

  it("visiteur : pas de lien de modification", async () => {
    renderAt(`/seller/organization/${ORG_ID}`);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("link", { name: "Modifier mon profil" })).not.toBeInTheDocument();
  });
});
