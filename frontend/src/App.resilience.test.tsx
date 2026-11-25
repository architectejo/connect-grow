import { configure, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "@/api/client";
import { tokenStorage } from "@/lib/tokens";
import App from "./App";

// Premier rendu jsdom (transformations à froid, Radix, i18n) : il dépasse les 5 s par défaut quand toute la suite tourne
// en parallèle sur la machine de développement. Délai explicite propre à ce fichier (ne dépend pas de vitest.config.ts).
vi.setConfig({ testTimeout: 20_000 });

beforeAll(async () => {
  configure({ asyncUtilTimeout: 5000 });
  // Préchauffe la page d'accueil (chargée par le premier test) : le premier cas ne paie plus l'import à froid
  await import("./pages/Index.tsx");
}, 60_000);

const original = apiClient.defaults.adapter;

const failWith = (status: number | null): AxiosAdapter => (config: InternalAxiosRequestConfig) => {
  if (status === null) return Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config));
  const response = { data: { detail: "x" }, status, statusText: "", headers: {}, config };
  return Promise.reject(new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, null, response));
};

describe("App : un échec d'API ne laisse jamais un écran blanc", () => {
  let errors: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, "", "/");
    errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => {
    apiClient.defaults.adapter = original;
    vi.restoreAllMocks();
  });

  const cases: [string, number | null][] = [
    ["API injoignable", null],
    ["API en erreur 500", 500],
    ["API en 401", 401],
    ["API en 403", 403],
    ["API en 404", 404],
  ];

  for (const [label, status] of cases) {
    it(`visiteur anonyme, ${label} : l'accueil s'affiche`, async () => {
      apiClient.defaults.adapter = failWith(status);
      render(<App />);
      expect(await screen.findByRole("main")).toBeInTheDocument();
      expect(screen.queryByText(/problème est survenu à l'affichage/i)).not.toBeInTheDocument();
    });

    it(`session ouverte, ${label} sur les contextes : l'accueil s'affiche`, async () => {
      tokenStorage.set("acces", "refresh");
      apiClient.defaults.adapter = failWith(status);
      render(<App />);
      expect(await screen.findByRole("main")).toBeInTheDocument();
      await waitFor(() => expect(document.body.textContent?.length).toBeGreaterThan(100));
      expect(screen.queryByText(/problème est survenu à l'affichage/i)).not.toBeInTheDocument();
      expect(errors.mock.calls.filter((c) => String(c[0]).includes("The above error"))).toHaveLength(0);
    });
  }
});
