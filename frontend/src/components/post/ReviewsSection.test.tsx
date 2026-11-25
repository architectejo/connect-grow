import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { Review, ReviewEligibility } from "@/api/types";
import { ReviewsSection } from "./ReviewsSection";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const review = (extra: Partial<Review> = {}): Review => ({
  id: "r1",
  post: "p1",
  is_mine: false,
  user_name: "Marie K.",
  offer_rating: 4,
  seller_rating: 5,
  content: "Vendeur ponctuel, annonce conforme.",
  source: "CONTACT",
  created_at: "2026-10-09T10:00:00+01:00",
  can_edit: false,
  ...extra,
});

const eligibility = (extra: Partial<ReviewEligibility> = {}): ReviewEligibility => ({
  can_review: false,
  reason: "no_contact",
  available_at: null,
  review_id: null,
  ...extra,
});

// Erreur 4xx : pas de nouvelle tentative automatique (shouldRetryQuery)
type ApiFailure = { response: { status: number; data: unknown } };

function mockApi(reviews: Review[] | ApiFailure, elig: ReviewEligibility | ApiFailure) {
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    const result = url.includes("eligibility") ? elig : reviews;
    if ("response" in result) throw result;
    return { data: result };
  });
}

const renderSection = (props: Partial<Parameters<typeof ReviewsSection>[0]> = {}) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ReviewsSection postId="p1" isOwner={false} currentUserId="u1" sellerName="Boutique Gombe" {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("ReviewsSection", () => {
  afterEach(() => vi.restoreAllMocks());

  it("affiche chaque avis avec ses deux notes, le libellé « Avis après contact » et la mention « modifié »", async () => {
    mockApi([review({ edited_at: "2026-10-09T11:00:00+01:00" })], eligibility());
    renderSection();
    const item = await screen.findByRole("listitem");
    expect(within(item).getByText("Marie K.")).toBeInTheDocument();
    expect(within(item).getByText("Avis après contact")).toBeInTheDocument();
    expect(within(item).getByRole("img", { name: "Note de l'offre : 4 sur 5" })).toBeInTheDocument();
    expect(within(item).getByRole("img", { name: "Note du vendeur : 5 sur 5" })).toBeInTheDocument();
    expect(within(item).getByText("(modifié)")).toBeInTheDocument();
  });

  it("propose « Donner mon avis » quand le serveur autorise, puis publie via le formulaire", async () => {
    mockApi([], eligibility({ can_review: true, reason: null }));
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: review({ is_mine: true, can_edit: true }) });
    renderSection();

    fireEvent.click(await screen.findByRole("button", { name: "Donner mon avis" }));
    const dialog = await screen.findByRole("dialog");
    const rate = (group: string, n: number) =>
      fireEvent.click(within(within(dialog).getByRole("radiogroup", { name: group })).getAllByRole("radio")[n - 1]);
    rate("Note de l'offre", 4);
    rate("Note du vendeur", 5);
    fireEvent.change(within(dialog).getByLabelText("Votre commentaire"), { target: { value: "Vendeur ponctuel, annonce conforme." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Publier mon avis" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("interactions/reviews/", {
        post: "p1",
        offer_rating: 4,
        seller_rating: 5,
        content: "Vendeur ponctuel, annonce conforme.",
      }),
    );
  });

  it("affiche la limite quotidienne (429) dans le formulaire", async () => {
    mockApi([], eligibility({ can_review: true, reason: null }));
    vi.spyOn(apiClient, "post").mockRejectedValue({
      response: { status: 429, data: { detail: "Limite", code: "daily_limit" }, headers: { "retry-after": "3600" } },
    });
    renderSection();

    fireEvent.click(await screen.findByRole("button", { name: "Donner mon avis" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(within(dialog).getByRole("radiogroup", { name: "Note de l'offre" })).getAllByRole("radio")[3]);
    fireEvent.click(within(within(dialog).getByRole("radiogroup", { name: "Note du vendeur" })).getAllByRole("radio")[4]);
    fireEvent.change(within(dialog).getByLabelText("Votre commentaire"), { target: { value: "Vendeur ponctuel, annonce conforme." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Publier mon avis" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Réessayez dans 1 heure");
  });

  it("sans droit d'avis : pas de bouton, une explication", async () => {
    mockApi([], eligibility({ reason: "no_contact" }));
    renderSection();
    expect(await screen.findByText(/après avoir contacté le vendeur/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Donner mon avis" })).not.toBeInTheDocument();
  });

  it("vendeur de l'offre : aucune requête d'éligibilité ni bouton", async () => {
    mockApi([review()], eligibility());
    renderSection({ isOwner: true, currentUserId: "u9" });
    await screen.findByRole("listitem");
    expect(vi.mocked(apiClient.get).mock.calls.some(([url]) => String(url).includes("eligibility"))).toBe(false);
    expect(screen.queryByRole("button", { name: "Donner mon avis" })).not.toBeInTheDocument();
  });

  it("avis de l'utilisateur verrouillé (masqué ou signalé) : aucune action, une explication", async () => {
    mockApi([review({ is_mine: true, can_edit: false })], eligibility({ reason: "already_reviewed" }));
    renderSection();
    expect(await screen.findByText("Cet avis ne peut plus être modifié ni supprimé.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Actions sur l'avis" })).not.toBeInTheDocument();
  });

  it("avis de l'utilisateur modifiable : le menu d'actions est proposé", async () => {
    mockApi([review({ is_mine: true, can_edit: true })], eligibility({ reason: "already_reviewed" }));
    renderSection();
    expect(await screen.findByRole("button", { name: "Actions sur l'avis" })).toBeInTheDocument();
  });

  it("erreur de chargement des avis : bouton Réessayer", async () => {
    mockApi({ response: { status: 403, data: {} } }, eligibility());
    renderSection();
    expect(await screen.findByText("Les avis n'ont pas pu être chargés.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Réessayer/ })).toBeInTheDocument();
  });

  it("éligibilité en erreur : Réessayer sans bouton « Donner mon avis »", async () => {
    mockApi([], { response: { status: 403, data: {} } });
    renderSection();
    expect(await screen.findByText("Impossible de vérifier si vous pouvez donner votre avis.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Donner mon avis" })).not.toBeInTheDocument();
  });
});

describe("ReviewsSection (visiteur anonyme)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("n'appelle pas l'endpoint d'éligibilité et propose de se connecter", async () => {
    mockApi([review()], eligibility());
    renderSection({ currentUserId: undefined });
    await screen.findByRole("listitem");
    expect(screen.getByRole("link", { name: "Se connecter" })).toBeInTheDocument();
    expect(vi.mocked(apiClient.get).mock.calls.some(([url]) => String(url).includes("eligibility"))).toBe(false);
  });

  it("avis contesté : « Modifier » reste proposé, « Supprimer » est désactivé avec explication", async () => {
    mockApi([review({ is_mine: true, can_edit: true, contest_report_id: "rep1" })], eligibility({ reason: "already_reviewed" }));
    renderSection();
    expect(await screen.findByText(/Le vendeur conteste le contact/)).toBeInTheDocument();
    fireEvent.keyDown(await screen.findByRole("button", { name: "Actions sur l'avis" }), { key: "Enter" });
    expect(await screen.findByRole("menuitem", { name: "Modifier" })).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("menuitem", { name: "Supprimer" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText(/Suppression impossible tant que le signalement est en cours/)).toBeInTheDocument();
  });

  it("avis contesté : l'auteur répond à la modération (author-response)", async () => {
    mockApi([review({ is_mine: true, can_edit: true, contest_report_id: "rep1" })], eligibility({ reason: "already_reviewed" }));
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: "rep1", status: "EN_ATTENTE", author_responded_at: "x" } });
    renderSection();
    fireEvent.click(await screen.findByRole("button", { name: "Répondre à la modération" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Votre réponse à la modération"), { target: { value: "Nous avons échangé." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Envoyer ma réponse" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("moderation/reports/rep1/author-response/", { author_response: "Nous avons échangé." }));
  });

  it("avis contesté déjà défendu : plus de bouton de réponse", async () => {
    mockApi([review({ is_mine: true, can_edit: true, contest_report_id: "rep1", contest_responded: true })], eligibility({ reason: "already_reviewed" }));
    renderSection();
    expect(await screen.findByText(/réponse a été transmise/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Répondre à la modération" })).not.toBeInTheDocument();
  });

  it("vendeur : peut signaler un contact fictif (REVIEW / CONTACT_FICTIF)", async () => {
    mockApi([review()], eligibility());
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: "x", status: "OPEN", created_at: "" } });
    renderSection({ isOwner: true, currentUserId: "u9" });
    const menu = await screen.findByRole("button", { name: "Actions sur l'avis" });
    fireEvent.keyDown(menu, { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: /Signaler un contact fictif/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Envoyer le signalement" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("moderation/reports/", expect.objectContaining({ target_type: "REVIEW", object_id: "r1", reason: "CONTACT_FICTIF" })),
    );
  });
});
