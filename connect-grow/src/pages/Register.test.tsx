import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeAll, describe, expect, it, vi } from "vitest";
import "@/i18n";
import Register from "./Register";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: false, login: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

beforeAll(() => {
  // Radix (case à cocher, bascules) mesure ses éléments : jsdom n'a pas ResizeObserver
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const renderAt = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={new QueryClient()}>
        <Register />
      </QueryClientProvider>
    </MemoryRouter>,
  );

describe("Register : destination conservée vers la connexion (L1-01-F2)", () => {
  it("?next=/organization-invitation est transmis au lien « Se connecter »", () => {
    renderAt("/register?next=%2Forganization-invitation");
    expect(screen.getByRole("link", { name: "Se connecter" })).toHaveAttribute("href", "/login?next=%2Forganization-invitation");
  });

  it("sans destination : lien simple vers /login", () => {
    renderAt("/register");
    expect(screen.getByRole("link", { name: "Se connecter" })).toHaveAttribute("href", "/login");
  });

  it("une destination externe est refusée (safeNext) : lien simple", () => {
    renderAt("/register?next=%2F%2Fevil.com");
    expect(screen.getByRole("link", { name: "Se connecter" })).toHaveAttribute("href", "/login");
  });
});
