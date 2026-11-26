import { useEffect, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import { INVITATION_TOKEN_KEY, clearInvitationToken, readInvitationToken, storeInvitationToken } from "@/lib/invitation-token";
import OrganizationInvitation from "./OrganizationInvitation";

const auth = vi.hoisted(() => ({ isAuthenticated: true, isLoading: false, user: { id: "compte-A" } as { id: string } | null, refreshUser: vi.fn() }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
const active = vi.hoisted(() => ({ setActive: vi.fn(), isError: false, contexts: [] as unknown[] }));
vi.mock("@/contexts/ActiveContextContext", () => ({ useActiveContext: () => active }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/layout/AppShell", () => ({ AppShell: ({ children }: { children: ReactNode }) => <main>{children}</main> }));

// Rendu jsdom + Radix + fenêtres chargées à la demande : 1 à 3 s par cas sur la machine de développement, davantage
// quand toute la suite tourne en parallèle. Délai explicite propre à ce fichier (ne dépend pas de vitest.config.ts).
vi.setConfig({ testTimeout: 20_000 });

beforeAll(async () => {
  configure({ asyncUtilTimeout: 5000 });
  await import("@/components/team/DeclineInvitationDialog");
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const TOKEN = "tok_ABC-123_secretsecretsecretsecretsecret00";
const ORG = "11111111-1111-4111-8111-111111111111";
const PREVIEW = {
  organization_name: "Boutique Lumière",
  org_type: "ENTREPRISE",
  role: "EDITOR",
  expires_at: "2026-11-16T08:00:00Z",
  invited_by_display_name: "Paul M.",
};
const ACCEPTED = { organization_id: ORG, organization_name: "Boutique Lumière", role: "EDITOR", membership_id: "22222222-2222-4222-8222-222222222222" };
const apiError = (status: number, code?: string, data: Record<string, unknown> = {}, headers: Record<string, string> = {}) => ({
  response: { status, data: code ? { detail: "Message du serveur", code } : data, headers },
});
const NETWORK = { isAxiosError: true, message: "Network Error" };

let client: QueryClient;
/** Locations vues par le routeur (sans rien écrire dans le DOM). */
const routerLocations: string[] = [];
function LocationProbe() {
  const location = useLocation();
  useEffect(() => {
    routerLocations.push(`${location.pathname}${location.search}${location.hash}|${JSON.stringify(location.state)}`);
  }, [location]);
  return null;
}
const openLink = (hash = `#token=${TOKEN}`) => window.history.replaceState(null, "", `/organization-invitation${hash}`);
/** Comme `BrowserRouter`, le routeur part de l'adresse courante (fragment compris). */
const renderPage = () => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const initial = `/organization-invitation${window.location.hash}`;
  // Arbre reconstruit à chaque rendu : React ne saute pas le nouveau rendu (même client, même routeur monté)
  const ui = () => (
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={client}>
        <LocationProbe />
        <Routes>
          <Route path="/organization-invitation" element={<OrganizationInvitation />} />
          <Route path="/organizations/:id" element={<p>Espace de l'organisation</p>} />
          <Route path="/dashboard" element={<p>Tableau de bord</p>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
  const view = render(ui());
  return { ...view, rerenderPage: () => view.rerender(ui()) };
};
const postsTo = (suffix: string) => vi.mocked(apiClient.post).mock.calls.filter((c) => String(c[0]).endsWith(suffix));

/** Aperçu réussi, puis la réponse donnée à l'acceptation ou au refus. */
const mockApi = (handlers: { accept?: unknown; decline?: unknown; preview?: unknown } = {}) =>
  vi.spyOn(apiClient, "post").mockImplementation(async (url: string) => {
    const pick = url.endsWith("/preview/") ? handlers.preview : url.endsWith("/accept/") ? handlers.accept : handlers.decline;
    if (pick instanceof Error || (pick && typeof pick === "object" && "response" in pick) || (pick && typeof pick === "object" && "isAxiosError" in pick)) throw pick;
    if (url.endsWith("/preview/")) return { data: pick ?? PREVIEW };
    if (url.endsWith("/accept/")) return { data: pick ?? ACCEPTED };
    return { status: 204, data: "" };
  });

beforeEach(() => {
  auth.isAuthenticated = true;
  auth.isLoading = false;
  online.value = true;
  active.setActive.mockClear();
  active.isError = false;
  active.contexts = [];
  auth.user = { id: "compte-A" };
  auth.refreshUser.mockClear();
  routerLocations.length = 0;
  sessionStorage.clear();
  localStorage.clear();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.info).mockClear();
  openLink();
});
afterEach(() => {
  vi.restoreAllMocks();
  clearInvitationToken();
  window.history.replaceState(null, "", "/");
});

describe("gestion du jeton à l'arrivée", () => {
  it("range le jeton du fragment en sessionStorage, efface la barre d'adresse, jamais en localStorage", async () => {
    mockApi();
    renderPage();
    expect(readInvitationToken()).toBe(TOKEN);
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain(TOKEN);
    expect(JSON.stringify({ ...localStorage })).not.toContain(TOKEN);
    await screen.findByText("Boutique Lumière");
  });

  it("Referrer-Policy no-referrer : balise meta présente sur la page, retirée au départ", () => {
    auth.isAuthenticated = false;
    const { unmount } = renderPage();
    expect(document.head.querySelector('meta[name="referrer"][content="no-referrer"]')).not.toBeNull();
    unmount();
    expect(document.head.querySelector('meta[name="referrer"]')).toBeNull();
  });

  it("aucun jeton : « Lien incomplet » sans appel réseau", () => {
    openLink("");
    const post = mockApi();
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "Lien incomplet" })).toBeInTheDocument();
    expect(screen.getByText(/^Ouvrez à nouveau le lien tel que vous l'avez reçu, en entier\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à l'accueil" })).toHaveAttribute("href", "/");
    expect(post).not.toHaveBeenCalled();
  });

  it("fragment non conforme : traité comme absent, effacé de la barre d'adresse, jamais rangé", () => {
    openLink("#token=a%20b%3Cscript");
    const post = mockApi();
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "Lien incomplet" })).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(sessionStorage.length).toBe(0);
    expect(post).not.toHaveBeenCalled();
  });

  it("retour après connexion : sans fragment, le jeton rangé est relu", async () => {
    openLink("");
    storeInvitationToken(TOKEN);
    const post = mockApi();
    renderPage();
    await screen.findByText("Boutique Lumière");
    expect(post).toHaveBeenCalledWith("accounts/organization-invitations/preview/", { token: TOKEN });
  });
});

describe("visiteur non connecté (E15, 4.4.1)", () => {
  beforeEach(() => {
    auth.isAuthenticated = false;
  });

  it("écran générique : aucun appel API, aucun nom d'organisation, ni rôle, ni date", () => {
    const post = mockApi();
    const get = vi.spyOn(apiClient, "get");
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "Vous avez reçu une invitation" })).toBeInTheDocument();
    expect(screen.getByText(/Connectez-vous ou créez un compte pour voir de quelle organisation il s'agit/)).toBeInTheDocument();
    expect(screen.getByText(/N'acceptez que les invitations de personnes que vous connaissez. N'ouvrez pas ce lien sur un appareil partagé/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/Éditeur|Analyste|Boutique|2026/);
  });

  it("« Se connecter » et « Créer un compte » portent ?next=/organization-invitation, le jeton reste rangé", () => {
    mockApi();
    renderPage();
    expect(screen.getByRole("link", { name: "Se connecter" })).toHaveAttribute("href", "/login?next=%2Forganization-invitation");
    expect(screen.getByRole("link", { name: "Créer un compte" })).toHaveAttribute("href", "/register?next=%2Forganization-invitation");
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("session en cours de vérification : squelette, ni écran visiteur ni appel (même après un délai)", async () => {
    auth.isAuthenticated = true;
    auth.isLoading = true;
    const post = mockApi();
    renderPage();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByText("Vous avez reçu une invitation")).not.toBeInTheDocument();
  });

  it("parcours complet : connecté ensuite, la page relit le jeton rangé et affiche l'aperçu", async () => {
    const post = mockApi();
    const { unmount } = renderPage();
    unmount();
    auth.isAuthenticated = true;
    openLink("");
    renderPage();
    await screen.findByText("Boutique Lumière");
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith("accounts/organization-invitations/preview/", { token: TOKEN });
  });
});

describe("visiteur connecté : aperçu (4.4.2)", () => {
  it("chargement : squelette, aucun bouton ; puis nom, type, inviteur, rôle et date de validité", async () => {
    let release: (value: unknown) => void = () => undefined;
    vi.spyOn(apiClient, "post").mockReturnValue(new Promise((resolve) => (release = resolve)) as never);
    renderPage();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Rejoindre l'organisation" })).not.toBeInTheDocument();
    release({ data: PREVIEW });
    expect(await screen.findByRole("heading", { level: 2, name: "Boutique Lumière" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Invitation à rejoindre une organisation" })).toBeInTheDocument();
    expect(screen.getByText("Paul M.")).toBeInTheDocument();
    expect(screen.getByText("Éditeur")).toBeInTheDocument();
    expect(screen.getByText("16 novembre 2026")).toBeInTheDocument();
    expect(screen.getByText(/Votre profil personnel et vos offres personnelles ne changent pas/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rejoindre l'organisation" })).toBeEnabled();
  });

  it("aucune mention de vérification, de note, de plan ni de prix (règles 2, 3 et 4)", async () => {
    mockApi();
    renderPage();
    await screen.findByText("Boutique Lumière");
    expect(document.body.textContent).not.toMatch(/vérifi|note|étoile|score|plan|abonnement|prix|\$|confiance/i);
  });

  it("l'aperçu est un POST avec le jeton dans le CORPS : URL sans jeton, clé de requête sans jeton", async () => {
    const post = mockApi();
    renderPage();
    await screen.findByText("Boutique Lumière");
    expect(post.mock.calls[0][0]).toBe("accounts/organization-invitations/preview/");
    expect(post.mock.calls[0][1]).toEqual({ token: TOKEN });
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.queryKey))).not.toContain(TOKEN);
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.queryKey))).toContain("org-invitation-preview");
  });
});

describe("hors ligne (4.6)", () => {
  it("boutons désactivés avec la raison, aucune action mise en file", async () => {
    online.value = false;
    const post = mockApi();
    renderPage();
    await screen.findByText("Boutique Lumière");
    expect(screen.getByRole("button", { name: "Rejoindre l'organisation" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Refuser l'invitation" })).toBeDisabled();
    expect(screen.getByText("Reconnectez-vous pour effectuer cette action.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rejoindre l'organisation" }));
    expect(postsTo("/accept/")).toHaveLength(0);
    expect(post).toHaveBeenCalledTimes(1);
    expect(readInvitationToken()).toBe(TOKEN);
  });
});

describe("accepter (4.4.3)", () => {
  it("succès : POST accept (jeton dans le corps), écran de succès, focus sur le titre, annonce unique, jeton supprimé", async () => {
    mockApi();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Rejoindre l'organisation" }));
    const title = await screen.findByRole("heading", { level: 1, name: "Vous avez rejoint Boutique Lumière" });
    expect(postsTo("/accept/")[0][1]).toEqual({ token: TOKEN });
    expect(screen.getByText("Vous avez le rôle Éditeur.")).toBeInTheDocument();
    await waitFor(() => expect(title).toHaveFocus());
    expect(readInvitationToken()).toBeNull();
    const live = screen.getAllByRole("status");
    expect(live).toHaveLength(1);
    await waitFor(() => expect(live[0]).toHaveTextContent("Vous avez rejoint l'organisation."));
    expect(live[0].textContent).not.toContain(TOKEN);
  });

  it("profil pas encore dans la liste : bouton désactivé avec indicateur pendant le rechargement de contexts/", async () => {
    active.contexts = [];
    mockApi();
    renderPage();
    // 1er rechargement : celui de l'acceptation (résolu) ; 2e : celui de l'écran de succès, retenu pour observer l'attente
    let release: () => void = () => undefined;
    const invalidate = vi
      .spyOn(client, "invalidateQueries")
      .mockResolvedValueOnce(undefined)
      .mockReturnValueOnce(new Promise<void>((resolve) => (release = resolve)));
    fireEvent.click(await screen.findByRole("button", { name: "Rejoindre l'organisation" }));
    await screen.findByRole("heading", { level: 1, name: /Vous avez rejoint/ });
    await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(2));
    const open = screen.getByRole("button", { name: "Ouvrir l'organisation" });
    expect(open).toBeDisabled();
    expect(open).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    release();
  });

  it("rechargement terminé sans l'organisation : message, « Réessayer » relance, puis ouverture une fois le profil présent", async () => {
    active.contexts = [];
    mockApi();
    const { rerenderPage } = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Rejoindre l'organisation" }));
    await screen.findByRole("heading", { level: 1, name: /Vous avez rejoint/ });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Votre nouveau profil n'est pas encore disponible.");
    const open = screen.getByRole("button", { name: "Ouvrir l'organisation" });
    expect(open).toBeDisabled();
    expect(open).not.toHaveAttribute("aria-busy");
    fireEvent.click(open);
    expect(active.setActive).not.toHaveBeenCalled();
    expect(screen.queryByText("Espace de l'organisation")).not.toBeInTheDocument();

    const invalidate = vi.spyOn(client, "invalidateQueries");
    fireEvent.click(within(alert).getByRole("button", { name: "Réessayer" }));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["contexts"] }));

    active.contexts = [{ type: "ORGANIZATION", id: ORG, name: "Boutique Lumière" }];
    rerenderPage();
    const ready = screen.getByRole("button", { name: "Ouvrir l'organisation" });
    expect(ready).toBeEnabled();
    fireEvent.click(ready);
    expect(active.setActive).toHaveBeenCalledWith({ type: "ORGANIZATION", id: ORG });
    expect(await screen.findByText("Espace de l'organisation")).toBeInTheDocument();
  });

  it("le profil actif ne change pas tout seul ; « Ouvrir l'organisation » le sélectionne puis ouvre l'organisation", async () => {
    active.contexts = [{ type: "ORGANIZATION", id: ORG, name: "Boutique Lumière" }];
    mockApi();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Rejoindre l'organisation" }));
    await screen.findByRole("heading", { level: 1, name: /Vous avez rejoint/ });
    expect(active.setActive).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ouvrir l'organisation" }));
    expect(active.setActive).toHaveBeenCalledWith({ type: "ORGANIZATION", id: ORG });
    expect(await screen.findByText("Espace de l'organisation")).toBeInTheDocument();
  });

  it("« Rester sur mon profil » ne change pas de profil", async () => {
    mockApi();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Rejoindre l'organisation" }));
    fireEvent.click(await screen.findByRole("link", { name: "Rester sur mon profil" }));
    expect(await screen.findByText("Tableau de bord")).toBeInTheDocument();
    expect(active.setActive).not.toHaveBeenCalled();
  });

  it("anti-doublon : un seul POST pendant l'appel", async () => {
    let release: (value: unknown) => void = () => undefined;
    vi.spyOn(apiClient, "post").mockImplementation((async (url: string) => {
      if (url.endsWith("/preview/")) return { data: PREVIEW };
      return new Promise((resolve) => (release = resolve));
    }) as never);
    renderPage();
    const button = await screen.findByRole("button", { name: "Rejoindre l'organisation" });
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    fireEvent.click(button);
    expect(postsTo("/accept/")).toHaveLength(1);
    release({ data: ACCEPTED });
    await screen.findByRole("heading", { level: 1, name: /Vous avez rejoint/ });
  });
});

describe("refuser (4.4.4)", () => {
  it("dialogue de confirmation avec focus initial sur « Garder l'invitation » ; refus : POST decline, écran, jeton supprimé", async () => {
    mockApi();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Refuser l'invitation" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Refuser cette invitation ?")).toBeInTheDocument();
    expect(within(dialog).getByText(/Le lien ne pourra plus être utilisé/)).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Garder l'invitation" })).toHaveFocus());
    fireEvent.click(within(dialog).getByRole("button", { name: "Refuser" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Invitation refusée" })).toBeInTheDocument();
    expect(postsTo("/decline/")[0][1]).toEqual({ token: TOKEN });
    expect(screen.getByText("Le lien ne peut plus être utilisé.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à l'accueil" })).toBeInTheDocument();
    expect(readInvitationToken()).toBeNull();
  });

  it("« Garder l'invitation » ferme sans appel", async () => {
    mockApi();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Refuser l'invitation" }));
    fireEvent.click(await screen.findByRole("button", { name: "Garder l'invitation" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(postsTo("/decline/")).toHaveLength(0);
    expect(readInvitationToken()).toBe(TOKEN);
  });
});

describe("erreurs (4.5) : neutres, jamais le nom de l'organisation", () => {
  const failOnAccept = async (error: unknown) => {
    mockApi({ accept: error });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Rejoindre l'organisation" }));
  };

  it("404 invitation_invalid à l'aperçu : message neutre, jeton supprimé, aucun nom", async () => {
    mockApi({ preview: apiError(404, "invitation_invalid") });
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Cette invitation n'est plus valable" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Le lien a peut-être expiré, été annulé ou déjà été utilisé.");
    expect(screen.getByRole("link", { name: "Retour à l'accueil" })).toBeInTheDocument();
    expect(readInvitationToken()).toBeNull();
    expect(document.body.textContent).not.toContain("Boutique");
  });

  it("404 invitation_invalid à l'acceptation : même message neutre, jeton supprimé", async () => {
    await failOnAccept(apiError(404, "invitation_invalid"));
    expect(await screen.findByRole("heading", { level: 1, name: "Cette invitation n'est plus valable" })).toBeInTheDocument();
    expect(readInvitationToken()).toBeNull();
    expect(document.body.textContent).not.toContain("Boutique");
  });

  it("400 {token} : traité comme invitation invalide", async () => {
    mockApi({ preview: apiError(400, undefined, { token: ["Ce champ est obligatoire."] }) });
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Cette invitation n'est plus valable" })).toBeInTheDocument();
  });

  it("403 phone_verification_required : lien vers la vérification du téléphone, jeton conservé", async () => {
    await failOnAccept(apiError(403, "phone_verification_required"));
    expect(await screen.findByRole("heading", { level: 1, name: "Vérifiez d'abord votre numéro" })).toBeInTheDocument();
    expect(screen.getByText(/Votre invitation reste valable/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vérifier mon numéro" })).toHaveAttribute("href", "/settings?tab=contact");
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("409 account_review_required : « Voir mes profils », jeton conservé, aucun chiffre de plafond", async () => {
    await failOnAccept(apiError(409, "account_review_required"));
    expect(await screen.findByRole("heading", { level: 1, name: "Examen du compte nécessaire" })).toBeInTheDocument();
    expect(screen.getByText(/doit être examiné par l'équipe Connecte\+ avant de rejoindre/)).toBeInTheDocument();
    expect(screen.getByRole("main").textContent).not.toMatch(/\d/);
    expect(screen.getByRole("link", { name: "Voir mes profils" })).toHaveAttribute("href", "/profiles");
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("409 already_member : message, « Voir mes profils », jeton supprimé", async () => {
    await failOnAccept(apiError(409, "already_member"));
    expect(await screen.findByRole("heading", { level: 1, name: "Vous faites déjà partie de cette organisation" })).toBeInTheDocument();
    expect(screen.getByText(/Cette invitation ne change pas votre rôle/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir mes profils" })).toBeInTheDocument();
    expect(readInvitationToken()).toBeNull();
  });

  it("403 DENY_SECURITY : « Action temporairement impossible »", async () => {
    await failOnAccept(apiError(403, "DENY_SECURITY"));
    expect(await screen.findByRole("heading", { level: 1, name: "Action temporairement impossible" })).toBeInTheDocument();
    expect(screen.getByText(/Cette action est temporairement impossible/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à l'accueil" })).toBeInTheDocument();
  });

  it("429 avec Retry-After : « Réessayer » désactivé, jeton conservé", async () => {
    await failOnAccept(apiError(429, undefined, {}, { "retry-after": "600" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Trop de tentatives" })).toBeInTheDocument();
    expect(screen.getByText("Patientez quelques minutes puis rouvrez le lien.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Réessayer" })).toBeDisabled());
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("429 sans délai lisible : « Réessayer » reste actif", async () => {
    await failOnAccept(apiError(429));
    expect(await screen.findByRole("heading", { level: 1, name: "Trop de tentatives" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeEnabled();
  });

  it("réseau coupé pendant l'acceptation : issue inconnue (jamais « non modifiée »), renvoi vers « Mes profils », listes invalidées, rien n'est mis en file", async () => {
    mockApi({ accept: NETWORK });
    renderPage();
    await screen.findByRole("button", { name: "Rejoindre l'organisation" });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    fireEvent.click(screen.getByRole("button", { name: "Rejoindre l'organisation" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion perdue pendant l'acceptation" })).toBeInTheDocument();
    expect(screen.getByText(/Nous ne savons pas si votre acceptation a été prise en compte/)).toBeInTheDocument();
    expect(screen.getByText(/vous pourrez y obtenir un nouveau code/)).toBeInTheDocument();
    expect(screen.queryByText(/n'a pas été modifiée/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir mes profils" })).toHaveAttribute("href", "/profiles");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["my-awaiting-invitations"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["contexts"] });
    await act(() => new Promise((resolve) => setTimeout(resolve, 30)));
    expect(postsTo("/accept/")).toHaveLength(1);
  });

  it("réseau coupé dès l'aperçu : même écran, jeton conservé", async () => {
    mockApi({ preview: NETWORK });
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion perdue" })).toBeInTheDocument();
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("401 (session expirée) : `clearSession` efface le jeton, la page affiche « Lien incomplet » (lien à rouvrir)", async () => {
    vi.spyOn(apiClient, "post").mockImplementation(async () => {
      // Ce que fait réellement l'application sur une session expirée : AUTH_EXPIRED_EVENT -> clearSession
      clearInvitationToken();
      auth.isAuthenticated = false;
      throw apiError(401);
    });
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Lien incomplet" })).toBeInTheDocument();
    expect(screen.getByText(/rouvrez-le depuis le message reçu/)).toBeInTheDocument();
    expect(readInvitationToken()).toBeNull();
    expect(screen.queryByRole("link", { name: "Se connecter" })).not.toBeInTheDocument();
  });

  it("compte inconnu (accounts/me/ en échec) : aucun aperçu, erreur générique, « Réessayer » recharge le compte", async () => {
    auth.user = null;
    const post = mockApi();
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Une erreur est survenue" })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(auth.refreshUser).toHaveBeenCalledTimes(1);
    expect(post).not.toHaveBeenCalled();
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("erreur inconnue (500) : message générique et « Réessayer », jeton conservé", async () => {
    await failOnAccept(apiError(500));
    expect(await screen.findByRole("heading", { level: 1, name: "Une erreur est survenue" })).toBeInTheDocument();
    expect(readInvitationToken()).toBe(TOKEN);
  });

  it("l'erreur est annoncée (role=alert) et le titre reçoit le focus", async () => {
    mockApi({ preview: apiError(404, "invitation_invalid") });
    renderPage();
    const title = await screen.findByRole("heading", { level: 1, name: "Cette invitation n'est plus valable" });
    expect(screen.getByRole("alert")).toContainElement(title);
    await waitFor(() => expect(title).toHaveFocus());
  });

  it("erreur au refus : même traitement (invitation invalide)", async () => {
    mockApi({ decline: apiError(404, "invitation_invalid") });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Refuser l'invitation" }));
    fireEvent.click(await screen.findByRole("button", { name: "Refuser" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Cette invitation n'est plus valable" })).toBeInTheDocument();
    expect(readInvitationToken()).toBeNull();
  });
});

describe("le jeton ne fuit dans aucun canal", () => {
  const consoleSpies = () => (["log", "info", "warn", "error", "debug"] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => undefined));

  const assertNoLeak = (spies: ReturnType<typeof consoleSpies>) => {
    expect(window.location.href).not.toContain(TOKEN);
    expect(window.location.hash).toBe("");
    expect(JSON.stringify({ ...localStorage })).not.toContain(TOKEN);
    expect(document.body.innerHTML).not.toContain(TOKEN);
    expect(document.head.innerHTML).not.toContain(TOKEN);
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => [q.queryKey, q.state.data]))).not.toContain(TOKEN);
    expect(JSON.stringify(client.getMutationCache().getAll().map((m) => [m.options.mutationKey, m.state.variables]))).not.toContain(TOKEN);
    expect(JSON.stringify([vi.mocked(toast.success).mock.calls, vi.mocked(toast.error).mock.calls, vi.mocked(toast.info).mock.calls])).not.toContain(TOKEN);
    for (const spy of spies) expect(JSON.stringify(spy.mock.calls)).not.toContain(TOKEN);
    for (const region of document.querySelectorAll("[aria-live]")) expect(region.textContent).not.toContain(TOKEN);
    // URL d'API : jamais le jeton (seul le corps du POST le porte)
    for (const call of vi.mocked(apiClient.post).mock.calls) expect(String(call[0])).not.toContain(TOKEN);
    for (const call of vi.mocked(apiClient.get).mock.calls) expect(JSON.stringify(call)).not.toContain(TOKEN);
  };

  it("parcours d'acceptation : stockage (sessionStorage seul, puis vidé), clés, DOM, URL, console, toasts, aria-live", async () => {
    const spies = consoleSpies();
    vi.spyOn(apiClient, "get");
    mockApi();
    renderPage();
    await screen.findByText("Boutique Lumière");
    assertNoLeak(spies);
    expect(readInvitationToken()).toBe(TOKEN); // seul canal autorisé
    fireEvent.click(screen.getByRole("button", { name: "Rejoindre l'organisation" }));
    await screen.findByRole("heading", { level: 1, name: /Vous avez rejoint/ });
    assertNoLeak(spies);
    expect(sessionStorage.length).toBe(0);
  });

  it("parcours d'erreur (jeton invalide, réseau, 429) : aucune fuite", async () => {
    for (const error of [apiError(404, "invitation_invalid"), NETWORK, apiError(429, undefined, {}, { "retry-after": "60" }), apiError(500)]) {
      const spies = consoleSpies();
      vi.spyOn(apiClient, "get");
      mockApi({ preview: error });
      openLink();
      const { unmount } = renderPage();
      await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
      assertNoLeak(spies);
      unmount();
      vi.restoreAllMocks();
    }
  });

  it("parcours visiteur : aucune fuite non plus", () => {
    auth.isAuthenticated = false;
    const spies = consoleSpies();
    vi.spyOn(apiClient, "get");
    vi.spyOn(apiClient, "post");
    renderPage();
    assertNoLeak(spies);
  });

  it("l'aperçu n'a qu'un POST et le décline un seul : tout passe par le corps", async () => {
    mockApi();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Refuser l'invitation" }));
    fireEvent.click(await screen.findByRole("button", { name: "Refuser" }));
    await screen.findByRole("heading", { level: 1, name: "Invitation refusée" });
    for (const call of vi.mocked(apiClient.post).mock.calls) {
      expect(call[1]).toEqual({ token: TOKEN });
      expect(call).toHaveLength(2); // aucun en-tête ni paramètre portant le jeton
    }
  });
});

describe("location du routeur et second lien (relecture F2)", () => {
  const OTHER = "zZ9-_otherTokenOtherTokenOtherTokenOther00";

  it("après l'arrivée, la location de React Router ne porte plus le jeton (remplacée, pas empilée)", async () => {
    mockApi();
    renderPage();
    await screen.findByText("Boutique Lumière");
    expect(routerLocations[0]).toContain(TOKEN); // point de départ, comme BrowserRouter
    expect(routerLocations[routerLocations.length - 1]).toBe("/organization-invitation|null");
    expect(routerLocations.slice(1).join()).not.toContain(TOKEN);
  });

  it("un second lien ouvert dans le même onglet (hashchange) remplace le premier et relance l'aperçu", async () => {
    const post = mockApi();
    renderPage();
    await screen.findByText("Boutique Lumière");
    window.history.replaceState(null, "", `/organization-invitation#token=${OTHER}`);
    act(() => {
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await waitFor(() => expect(post).toHaveBeenLastCalledWith("accounts/organization-invitations/preview/", { token: OTHER }));
    expect(readInvitationToken()).toBe(OTHER);
    expect(window.location.hash).toBe("");
    expect(routerLocations[routerLocations.length - 1]).not.toContain(OTHER);
  });

  it("un second lien après un refus réussi : on repart de l'aperçu", async () => {
    mockApi();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Refuser l'invitation" }));
    fireEvent.click(await screen.findByRole("button", { name: "Refuser" }));
    await screen.findByRole("heading", { level: 1, name: "Invitation refusée" });
    window.history.replaceState(null, "", `/organization-invitation#token=${OTHER}`);
    act(() => {
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(await screen.findByRole("heading", { level: 2, name: "Boutique Lumière" })).toBeInTheDocument();
  });
});

describe("onglet partagé (audit S2)", () => {
  it("jeton lié au compte A : le compte B connecté ensuite voit « Lien incomplet », sans appel, jeton effacé", async () => {
    const post = mockApi();
    const first = renderPage();
    await screen.findByText("Boutique Lumière");
    first.unmount();
    post.mockClear();

    auth.user = { id: "compte-B" };
    openLink("");
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Lien incomplet" })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    expect(readInvitationToken()).toBeNull();
  });

  it("jeton rangé depuis plus de 60 minutes : « Lien incomplet », sans appel", () => {
    openLink("");
    storeInvitationToken(TOKEN, Date.now() - 61 * 60 * 1000);
    const post = mockApi();
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "Lien incomplet" })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
  });
});

describe("focus", () => {
  it("une erreur remplacée directement par une autre (429 puis 404 au nouvel essai) redonne le focus au titre", async () => {
    const post = mockApi({ preview: apiError(429) });
    renderPage();
    const first = await screen.findByRole("heading", { level: 1, name: "Trop de tentatives" });
    await waitFor(() => expect(first).toHaveFocus());
    first.blur();
    post.mockImplementation(async () => {
      throw apiError(404, "invitation_invalid");
    });
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    const second = await screen.findByRole("heading", { level: 1, name: "Cette invitation n'est plus valable" });
    await waitFor(() => expect(second).toHaveFocus());
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// L1-01-F2bis : aperçu enrichi, invitation Administrateur (202 + code de rattachement), retrait de la demande
describe("invitations v2 (spec D2 §9)", () => {
  const SENTINEL = "482913";
  const INVITATION_ID = "44444444-4444-4444-8444-444444444441";
  const ADMIN_PREVIEW = {
    ...PREVIEW,
    role: "ADMIN",
    scope: { type: "ORGANIZATION", id: null },
    capabilities: ["contact.manage_channels", "message.reply", "org.leave", "org.manage_members", "org.view_internal", "stats.view", "zz.unknown"],
    requires_confirmation: true,
  };
  const AWAITING_202 = {
    status: "AWAITING_CONFIRMATION",
    invitation_id: INVITATION_ID,
    organization_name: "Boutique Lumière",
    role: "ADMIN",
    confirmation_expires_at: "2026-11-28T13:05:00Z",
    confirmation_code: SENTINEL,
  };

  const acceptAdmin = async () => {
    const post = mockApi({ preview: ADMIN_PREVIEW, accept: AWAITING_202 });
    const view = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Accepter l'invitation" }));
    await screen.findByRole("heading", { level: 1, name: "Demande envoyée à « Boutique Lumière »" });
    return { post, ...view };
  };
  const failOnAcceptV2 = async (error: unknown) => {
    mockApi({ preview: ADMIN_PREVIEW, accept: error });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Accepter l'invitation" }));
  };

  it("aperçu Administrateur : émetteur, rôle, périmètre, accès regroupés, limites, avertissement AVANT le bouton « Accepter l'invitation »", async () => {
    mockApi({ preview: ADMIN_PREVIEW });
    renderPage();
    const button = await screen.findByRole("button", { name: "Accepter l'invitation" });
    expect(screen.getByText("Paul M.")).toBeInTheDocument();
    expect(screen.getByText("Périmètre")).toBeInTheDocument();
    expect(screen.getByText("Toute l'organisation")).toBeInTheDocument();
    expect(screen.getByText("Accès")).toBeInTheDocument();
    for (const group of ["Organisation", "Équipe", "Contact", "Messages", "Statistiques"]) expect(screen.getByRole("heading", { level: 3, name: group })).toBeInTheDocument();
    expect(screen.getByText("Inviter et retirer des membres")).toBeInTheDocument();
    expect(screen.getByText("et 1 autre accès")).toBeInTheDocument();
    expect(screen.getByText(/ne permet ni de nommer un administrateur principal, ni d'archiver/)).toBeInTheDocument();
    const alertTitle = screen.getByText("Confirmation nécessaire");
    expect(screen.getByText(/Elle verra votre nom abrégé et les deux derniers chiffres de votre numéro de téléphone/)).toBeInTheDocument();
    expect(screen.getByText(/vous recevrez un code à 6 chiffres. Vous le donnerez de vive voix/)).toBeInTheDocument();
    expect(alertTitle.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(button).toHaveAccessibleDescription(/Confirmation nécessaire/);
    expect(screen.getByText(/Après confirmation, vous pourrez quitter l'organisation à tout moment/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rejoindre l'organisation" })).not.toBeInTheDocument();
  });

  it("aperçu Éditeur v2 : accès listés, ni avertissement de confirmation ni limites d'administrateur", async () => {
    mockApi({ preview: { ...PREVIEW, scope: { type: "ORGANIZATION", id: null }, capabilities: ["offer.publish", "review.reply"], requires_confirmation: false } });
    renderPage();
    expect(await screen.findByRole("button", { name: "Rejoindre l'organisation" })).toBeEnabled();
    expect(screen.getByText("Publier des offres")).toBeInTheDocument();
    expect(screen.getByText("Répondre aux avis")).toBeInTheDocument();
    expect(screen.queryByText("Confirmation nécessaire")).not.toBeInTheDocument();
    expect(screen.queryByText(/ne permet ni de nommer/)).not.toBeInTheDocument();
  });

  it("202 : écran « Demande envoyée », code en grand (groupes masqués, lecture chiffre par chiffre), focus sur le titre, aucune bascule de profil", async () => {
    await acceptAdmin();
    const title = screen.getByRole("heading", { level: 1, name: "Demande envoyée à « Boutique Lumière »" });
    await waitFor(() => expect(title).toHaveFocus());
    expect(screen.getByText(/Vous avez accepté le rôle Administrateur/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Votre code de confirmation" })).toBeInTheDocument();
    expect(screen.getByText("482 913")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("4 8 2 9 1 3")).toHaveClass("sr-only");
    expect(screen.getByText(/Donnez ce code de vive voix/)).toBeInTheDocument();
    expect(screen.getByText(/ne l'envoyez pas par message/)).toBeInTheDocument();
    expect(screen.getByText(/Ce code ne sera plus affiché quand vous quitterez cette page/)).toBeInTheDocument();
    expect(screen.getByText(/^Confirmation attendue avant le/)).toBeInTheDocument();
    expect(screen.getByText(/Vous n'avez encore aucun accès à l'organisation/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir mes profils" })).toHaveAttribute("href", "/profiles");
    expect(screen.getByRole("button", { name: "Retirer ma demande" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Copier|Partager/ })).not.toBeInTheDocument();
    expect(active.setActive).not.toHaveBeenCalled();
    expect(readInvitationToken()).toBeNull();
  });

  it("SENTINELLE 202 : le code n'est ni annoncé, ni en toast, ni stocké, ni en cache de requêtes ou de mutations, ni dans l'URL, un attribut ou la console", async () => {
    const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level));
    await acceptAdmin();
    const live = screen.getByRole("status");
    await waitFor(() => expect(live).toHaveTextContent("Demande envoyée. Votre code de confirmation est affiché à l'écran."));
    const channels = {
      live: Array.from(document.querySelectorAll("[aria-live], [role=status], [role=alert]")).map((n) => n.textContent).join("|"),
      toasts: JSON.stringify([vi.mocked(toast.success).mock.calls, vi.mocked(toast.error).mock.calls, vi.mocked(toast.info).mock.calls]),
      session: JSON.stringify({ ...sessionStorage }),
      local: JSON.stringify({ ...localStorage }),
      queries: JSON.stringify(client.getQueryCache().getAll().map((q) => [q.queryKey, q.state.data])),
      mutations: JSON.stringify(client.getMutationCache().getAll().map((m) => [m.state.variables, m.state.data])),
      url: window.location.href + JSON.stringify(routerLocations),
      attributes: Array.from(document.querySelectorAll("*")).flatMap((n) => Array.from(n.attributes).map((a) => a.value)).join("|"),
      console: JSON.stringify(consoleSpies.map((spy) => spy.mock.calls)),
    };
    expect(Object.entries(channels).filter(([, value]) => value.includes(SENTINEL)).map(([name]) => name)).toEqual([]);
  });

  it("le code disparaît au démontage de la page", async () => {
    const { unmount } = await acceptAdmin();
    expect(document.body.textContent).toContain("482 913");
    unmount();
    expect(document.body.innerHTML).not.toContain("482 913");
    expect(JSON.stringify(client.getMutationCache().getAll().map((m) => m.state.data))).not.toContain(SENTINEL);
  });

  it("« Retirer ma demande » : focus sur « Garder la demande », POST withdraw/, écran « Demande retirée », code effacé", async () => {
    const { post } = await acceptAdmin();
    fireEvent.click(screen.getByRole("button", { name: "Retirer ma demande" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Retirer votre demande pour « Boutique Lumière » ?" });
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Garder la demande" })).toHaveFocus());
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer ma demande" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Demande retirée" })).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith(`accounts/organization-invitations/${INVITATION_ID}/withdraw/`);
    expect(screen.getByText("Vous ne rejoindrez pas cette organisation. Le lien ne peut plus être utilisé.")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("482 913");
  });

  it("bfcache : à `pagehide`, le code est effacé ; l'écran dit « Code masqué » et renvoie vers « Mes profils »", async () => {
    await acceptAdmin();
    expect(document.body.textContent).toContain("482 913");
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    expect(await screen.findByText("Code masqué")).toBeInTheDocument();
    expect(screen.getByText(/obtenez-en un nouveau depuis « Mes profils »/)).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain("482 913");
    expect(document.body.innerHTML).not.toContain(SENTINEL);
    expect(screen.getByRole("heading", { level: 1, name: "Demande envoyée à « Boutique Lumière »" })).toBeInTheDocument();
  });

  it("retrait alors que la demande n'est plus en attente : toast, écran sans code « n'est plus en attente »", async () => {
    await acceptAdmin();
    vi.mocked(apiClient.post).mockRejectedValueOnce(apiError(409, "invitation_not_awaiting_confirmation"));
    fireEvent.click(screen.getByRole("button", { name: "Retirer ma demande" }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer ma demande" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Cette demande n'est plus en attente" })).toBeInTheDocument();
    expect(toast.info).toHaveBeenCalledWith("Cette invitation n'est plus en attente.");
    expect(document.body.innerHTML).not.toContain("482 913");
  });

  it("409 already_awaiting_confirmation : « Une demande est déjà en attente », « Voir mes profils », jeton conservé", async () => {
    await failOnAcceptV2(apiError(409, "already_awaiting_confirmation"));
    expect(await screen.findByRole("heading", { level: 1, name: "Une demande est déjà en attente" })).toBeInTheDocument();
    expect(screen.getByText(/retirez cette demande depuis « Mes profils »/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir mes profils" })).toBeInTheDocument();
    expect(readInvitationToken()).toBe(TOKEN);
  });
});
