import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { ReviewForm } from "./ReviewForm";

const rate = (group: string, n: number) => {
  const radios = screen.getByRole("radiogroup", { name: group }).querySelectorAll<HTMLElement>('[role="radio"]');
  fireEvent.click(radios[n - 1]);
};

describe("ReviewForm", () => {
  it("expose deux groupes de notes et un commentaire libellé", () => {
    render(<ReviewForm submitLabel="Publier mon avis" onSubmit={() => {}} />);
    expect(screen.getByRole("radiogroup", { name: "Note de l'offre" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Note du vendeur" })).toBeInTheDocument();
    expect(screen.getByLabelText("Votre commentaire")).toBeInTheDocument();
  });

  it("reste bloqué tant qu'une note manque ou que le commentaire compte moins de 10 caractères", () => {
    render(<ReviewForm submitLabel="Publier mon avis" onSubmit={() => {}} />);
    const submit = screen.getByRole("button", { name: "Publier mon avis" });
    expect(submit).toBeDisabled();

    rate("Note de l'offre", 4);
    fireEvent.change(screen.getByLabelText("Votre commentaire"), { target: { value: "123456789" } });
    expect(submit).toBeDisabled();

    rate("Note du vendeur", 5);
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Votre commentaire"), { target: { value: "1234567890" } });
    expect(submit).toBeEnabled();
  });

  it("envoie les deux notes et le commentaire nettoyé", () => {
    const onSubmit = vi.fn();
    render(<ReviewForm submitLabel="Publier mon avis" onSubmit={onSubmit} />);
    rate("Note de l'offre", 4);
    rate("Note du vendeur", 5);
    fireEvent.change(screen.getByLabelText("Votre commentaire"), { target: { value: "  Vendeur ponctuel et sérieux.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Publier mon avis" }));
    expect(onSubmit).toHaveBeenCalledWith({ offer_rating: 4, seller_rating: 5, content: "Vendeur ponctuel et sérieux." });
  });

  it("préremplit une modification et affiche l'erreur du serveur", () => {
    render(
      <ReviewForm
        initial={{ offer_rating: 3, seller_rating: 2, content: "Livraison un peu lente." }}
        submitLabel="Enregistrer"
        error="Le délai pour modifier cet avis est dépassé."
        onSubmit={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
    expect(screen.getByLabelText("Votre commentaire")).toHaveValue("Livraison un peu lente.");
    expect(screen.getByRole("alert")).toHaveTextContent("Le délai pour modifier cet avis est dépassé.");
  });

  it("limite le commentaire à 500 caractères", () => {
    render(<ReviewForm submitLabel="Publier mon avis" onSubmit={() => {}} />);
    fireEvent.change(screen.getByLabelText("Votre commentaire"), { target: { value: "a".repeat(600) } });
    expect(screen.getByLabelText("Votre commentaire")).toHaveValue("a".repeat(500));
  });
});
