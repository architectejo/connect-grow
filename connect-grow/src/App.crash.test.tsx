import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./components/layout/PwaUpdater", () => ({ PwaUpdater: () => null }));
vi.mock("./pages/Index.tsx", () => ({
  default: () => {
    throw new Error("page cassée");
  },
}));

describe("App : une exception d'affichage ne laisse pas un écran blanc", () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, "", "/");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  it("affiche l'écran de secours quand la page plante", async () => {
    render(<App />);
    expect(await screen.findByText("Un problème est survenu à l'affichage")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recharger la page" })).toBeInTheDocument();
  });
});
