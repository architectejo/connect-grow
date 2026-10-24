import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary, isChunkLoadError } from "./ErrorBoundary";

const Boom = ({ message = "boum" }: { message?: string }): never => {
  throw new Error(message);
};

describe("ErrorBoundary", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    sessionStorage.clear();
    consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  it("affiche les enfants quand tout va bien", () => {
    render(
      <ErrorBoundary>
        <p>contenu</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("contenu")).toBeInTheDocument();
  });

  it("affiche l'écran de secours en français, replie le détail et journalise l'erreur", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Un problème est survenu à l'affichage")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recharger la page" })).toBeInTheDocument();
    const details = screen.getByText("Détail technique").closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent("Error: boum");
    expect(consoleError.mock.calls.some((c) => String(c[0]).includes("[ErrorBoundary]"))).toBe(true);
  });

  it("« Recharger la page » recharge la page", () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Recharger la page" }));
    expect(reload).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("réaffiche les enfants quand resetKey change", () => {
    let fail = true;
    const Maybe = () => (fail ? <Boom /> : <p>rétabli</p>);
    const { rerender } = render(
      <ErrorBoundary resetKey="/a">
        <Maybe />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fail = false;
    rerender(
      <ErrorBoundary resetKey="/b">
        <Maybe />
      </ErrorBoundary>,
    );
    expect(screen.getByText("rétabli")).toBeInTheDocument();
  });

  it("recharge une seule fois après l'échec d'un fichier de page", () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    const view = (
      <ErrorBoundary>
        <Boom message="Failed to fetch dynamically imported module: /src/pages/X.tsx" />
      </ErrorBoundary>
    );
    render(view);
    render(view);
    expect(reload).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("reconnaît les erreurs de chargement de fichier", () => {
    expect(isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: x"))).toBe(true);
    expect(isChunkLoadError(new Error("Cannot read properties of undefined"))).toBe(false);
  });
});
