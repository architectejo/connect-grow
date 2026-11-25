import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import "@/i18n";
import { RatingBlock, RatingValue } from "./Rating";

describe("RatingValue", () => {
  it("annonce la note de l'offre avec un libellé accessible complet", () => {
    render(<RatingValue kind="offer" rating={{ average: 4.2, count: 5 }} />);
    expect(screen.getByRole("img", { name: "Note de l'offre : 4,2 sur 5, 5 avis" })).toBeInTheDocument();
    expect(screen.getByText("4,2")).toBeInTheDocument();
  });

  it("sous le seuil (average null) : pas de moyenne, mais le nombre d'avis reste affiché", () => {
    render(<RatingValue kind="offer" rating={{ average: null, count: 2 }} />);
    expect(screen.getByRole("img", { name: "Note de l'offre : pas encore assez d'avis, 2 avis" })).toBeInTheDocument();
    expect(screen.getByText("Pas encore assez d'avis (2 avis)")).toBeInTheDocument();
    expect(screen.queryByText(/\d,\d/)).not.toBeInTheDocument();
  });

  it("sans aucun avis : « Pas encore d'avis », jamais une note neutre", () => {
    render(<RatingValue kind="seller" rating={{ average: null, count: 0 }} />);
    expect(screen.getByRole("img", { name: "Note du vendeur : pas encore d'avis" })).toBeInTheDocument();
    expect(screen.getByText("Pas encore d'avis")).toBeInTheDocument();
  });

  it("n'affiche rien quand l'API ne renvoie pas la note", () => {
    const { container } = render(<RatingValue kind="offer" rating={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("RatingBlock", () => {
  it("garde deux blocs distincts pour l'offre et le vendeur, avec l'ancienneté sous la note du vendeur", () => {
    render(
      <>
        <RatingBlock kind="offer" rating={{ average: 4.2, count: 5 }} />
        <RatingBlock kind="seller" rating={{ average: 3.9, count: 8 }} footer="Sur Connecte+ depuis mars 2025" />
      </>,
    );
    expect(screen.getByRole("img", { name: "Note de l'offre : 4,2 sur 5, 5 avis" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Note du vendeur : 3,9 sur 5, 8 avis" })).toBeInTheDocument();
    expect(screen.getByTestId("rating-block-seller")).toHaveTextContent("Sur Connecte+ depuis mars 2025");
    expect(screen.getByTestId("rating-block-offer")).not.toHaveTextContent("Sur Connecte+");
  });

  it("montre « Pas encore assez d'avis » et le compte sous le seuil", () => {
    render(<RatingBlock kind="seller" rating={{ average: null, count: 2 }} />);
    expect(screen.getByText("Pas encore assez d'avis (2 avis)")).toBeInTheDocument();
  });
});
