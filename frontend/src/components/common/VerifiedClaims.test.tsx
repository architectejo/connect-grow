import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import type { Post, VerifiedClaim } from "@/api/types";
import { PostCard } from "./PostCard";
import { SellerCard } from "./SellerCard";
import { SellerTypeBadge } from "./SellerTypeBadge";
import { VerifiedClaims } from "./VerifiedClaims";
import identity from "@/api/__fixtures__/backend-identity.json";

vi.mock("@/hooks/use-features", () => ({ useFeatures: () => ({ exchangeEnabled: false }) }));

const claim = (code: string, label = code): VerifiedClaim => ({ code, label, verified_at: "2026-09-12T10:00:00Z" });
const RCCM = claim("RCCM_VERIFIED", "RCCM vérifié");
const IDN = claim("NATIONAL_ID_VERIFIED", "Identification nationale vérifiée");
const REP = claim("REPRESENTATIVE_VERIFIED", "Représentant vérifié");
const NONE = { complete: false, label: null };

describe("VerifiedClaims (règle 3 : une mention dit ce qui a été vérifié)", () => {
  it("affiche une pastille précise par mention, dans une liste nommée", () => {
    render(<VerifiedClaims claims={[RCCM, IDN]} summary={NONE} />);
    const list = screen.getByRole("list", { name: "Vérifications" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("RCCM vérifié"), expect.stringContaining("Identification nationale vérifiée")]),
    );
  });

  it("n'affiche jamais « Vérifié » seul, ni « garanti »", () => {
    const { container } = render(<VerifiedClaims claims={[RCCM, IDN, REP]} summary={{ complete: true, label: "Organisation vérifiée" }} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/(^|\s)Vérifié(\s|$)/);
    expect(text).not.toMatch(/garanti|certifi|de confiance/i);
  });

  it("« Organisation vérifiée » seulement si le serveur confirme, et toujours suivie de la liste des mentions", () => {
    const { rerender } = render(<VerifiedClaims claims={[RCCM]} summary={NONE} />);
    expect(screen.queryByText("Organisation vérifiée")).not.toBeInTheDocument();
    rerender(<VerifiedClaims claims={[RCCM, IDN, REP]} summary={{ complete: true, label: "Organisation vérifiée" }} />);
    expect(screen.getByText("Organisation vérifiée")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("jamais « Organisation vérifiée » sans mention (liste vide : rien n'est affiché, pas de « Non vérifié »)", () => {
    const { container } = render(<VerifiedClaims claims={[]} summary={{ complete: true, label: "Organisation vérifiée" }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("forme compacte : deux mentions puis +N, sans synthèse ni aide", () => {
    render(<VerifiedClaims compact claims={[RCCM, IDN, REP]} summary={{ complete: true, label: "Organisation vérifiée" }} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3); // 2 mentions + « +1 »
    expect(screen.getByLabelText("et 1 autre mention de vérification")).toHaveTextContent("+1");
    expect(screen.queryByText("Organisation vérifiée")).not.toBeInTheDocument();
    expect(screen.queryByText("Que signifie cette mention ?")).not.toBeInTheDocument();
  });

  it("propose l'aide « Que signifie cette mention ? » en forme complète", () => {
    render(<VerifiedClaims claims={[RCCM]} summary={NONE} />);
    expect(screen.getByRole("button", { name: "Que signifie cette mention ?" })).toBeInTheDocument();
  });

  it("un code inconnu du dictionnaire retombe sur le libellé du serveur", () => {
    render(<VerifiedClaims claims={[claim("NOUVELLE_PIECE_VERIFIED", "Nouvelle pièce vérifiée")]} summary={NONE} />);
    expect(screen.getByText("Nouvelle pièce vérifiée")).toBeInTheDocument();
  });
});

describe("SellerTypeBadge", () => {
  it("dit toujours le type de vendeur par un texte", () => {
    const { rerender } = render(<SellerTypeBadge contextType="USER" />);
    expect(screen.getByText("Particulier")).toBeInTheDocument();
    rerender(<SellerTypeBadge contextType="PROVIDER" />);
    expect(screen.getByText("Prestataire")).toBeInTheDocument();
    rerender(<SellerTypeBadge contextType="ORGANIZATION" orgType="BOUTIQUE" />);
    expect(screen.getByText("Organisation · Boutique")).toBeInTheDocument();
    rerender(<SellerTypeBadge contextType="ORGANIZATION" orgType="ONG" compact />);
    expect(screen.getByText("ONG")).toBeInTheDocument();
  });
});

describe("SellerCard et PostCard avec les vendeurs réels de l'API d'intégration", () => {
  const post = identity.post_detail_organization as unknown as Post;

  it("fiche d'offre : nom, type, mention précise et ancienneté ; aucun badge « Vérifié » seul", () => {
    const { container } = render(
      <MemoryRouter>
        <SellerCard seller={post.seller} rating={post.seller_rating} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Atelier Test")).toBeInTheDocument();
    expect(screen.getByText("Organisation · Entreprise")).toBeInTheDocument();
    expect(screen.getByText("RCCM vérifié")).toBeInTheDocument();
    expect(screen.getByText(/Sur Connecte\+ depuis/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/(^|\s)Vérifié(\s|$)/);
    expect(screen.getAllByRole("link")[0]).toHaveAttribute("href", `/seller/organization/${post.seller.context_id}`);
  });

  it("carte d'annonce : type compact et mention ; « Sponsorisé » reste séparé des mentions de vérification", () => {
    render(
      <MemoryRouter>
        <PostCard post={{ ...post, badges: ["sponsored"] }} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Sponsorisé")).toBeInTheDocument();
    expect(screen.getByText("Entreprise")).toBeInTheDocument();
    expect(screen.getByText("RCCM vérifié")).toBeInTheDocument();
    const sponsored = screen.getByText("Sponsorisé").closest("span");
    expect(sponsored?.textContent).not.toMatch(/vérifi/i);
  });

  it("compte personnel : nom abrégé et type « Particulier », pas de mention", () => {
    const user = identity.post_detail_user as unknown as Post;
    render(
      <MemoryRouter>
        <PostCard post={user} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Particulier")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Vérifications" })).not.toBeInTheDocument();
  });
});
