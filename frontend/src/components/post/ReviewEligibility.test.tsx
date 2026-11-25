import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import type { ReviewEligibility } from "@/api/types";
import { ReviewEligibilityPanel } from "./ReviewEligibility";

type PanelProps = Parameters<typeof ReviewEligibilityPanel>[0];

const renderPanel = (props: Partial<PanelProps>) =>
  render(
    <MemoryRouter>
      <ReviewEligibilityPanel postId="p1" isAuthenticated isLoading={false} isError={false} onRetry={() => {}} onGiveReview={() => {}} {...props} />
    </MemoryRouter>,
  );

const refusal = (reason: ReviewEligibility["reason"], extra: Partial<ReviewEligibility> = {}): ReviewEligibility => ({
  can_review: false,
  reason,
  available_at: null,
  review_id: null,
  ...extra,
});

describe("ReviewEligibilityPanel", () => {
  it("affiche « Donner mon avis » quand le serveur dit can_review", () => {
    const onGiveReview = vi.fn();
    renderPanel({ eligibility: { can_review: true, reason: null, available_at: null, review_id: null }, onGiveReview });
    fireEvent.click(screen.getByRole("button", { name: "Donner mon avis" }));
    expect(onGiveReview).toHaveBeenCalledOnce();
  });

  it.each([
    ["no_contact", /après avoir contacté le vendeur/],
    ["already_reviewed", /déjà donné votre avis/],
    ["offer_unavailable", /n'accepte plus d'avis/],
    ["contact_rejected", /contact n'a pas été retenu/],
    ["recently_deleted", /récemment supprimé/],
  ] as const)("sans droit (%s) : pas de bouton, un texte d'explication", (reason, text) => {
    renderPanel({ eligibility: refusal(reason) });
    expect(screen.queryByRole("button", { name: "Donner mon avis" })).not.toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("visiteur non connecté : propose de se connecter, sans données d'éligibilité", () => {
    renderPanel({ isAuthenticated: false, eligibility: undefined });
    expect(screen.queryByRole("button", { name: "Donner mon avis" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Se connecter" })).toBeInTheDocument();
  });

  it("trop tôt : donne la date de disponibilité à l'heure de Kinshasa", () => {
    renderPanel({ eligibility: refusal("too_early", { available_at: "2026-10-10T13:05:00Z" }) });
    // 13:05 UTC = 14:05 à Kinshasa (UTC+1)
    expect(screen.getByText(/à partir du 10 octobre.*14:05/)).toBeInTheDocument();
  });

  it("compte trop récent : donne la date d'ouverture à l'heure de Kinshasa", () => {
    renderPanel({ eligibility: refusal("account_too_new", { available_at: "2026-10-10T13:05:00Z" }) });
    expect(screen.getByText(/compte est trop récent.*à partir du 10 octobre.*14:05/)).toBeInTheDocument();
  });

  it("compte trop récent sans date : message sans date", () => {
    renderPanel({ eligibility: refusal("account_too_new") });
    expect(screen.getByText(/compte est trop récent.*un peu plus tard/)).toBeInTheDocument();
  });

  it("propriétaire de l'offre : rien n'est proposé", () => {
    const { container } = renderPanel({ eligibility: refusal("own_offer") });
    expect(container).toBeEmptyDOMElement();
  });

  it("404 offer_not_found : « Annonce introuvable »", () => {
    renderPanel({ isError: true, error: { response: { status: 404, data: { code: "offer_not_found" } } } });
    expect(screen.getByText("Annonce introuvable.")).toBeInTheDocument();
  });

  it("chargement : squelette sans bouton", () => {
    renderPanel({ isLoading: true });
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("erreur : propose de réessayer, sans déduire de droit d'avis", () => {
    const onRetry = vi.fn();
    renderPanel({ isError: true, onRetry });
    expect(screen.queryByRole("button", { name: "Donner mon avis" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Réessayer/ }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
