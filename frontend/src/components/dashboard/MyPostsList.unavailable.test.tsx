import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import fixture from "@/api/__fixtures__/contexts.json";
import { MyPostsList } from "./MyPostsList";

const state = vi.hoisted(() => ({ unavailable: [] as { id: string; name: string }[], contexts: [{ type: "USER" }] as { type: string }[] }));
vi.mock("@/contexts/ActiveContextContext", () => ({
  useActiveContext: () => ({ active: { type: "USER", id: "u" }, contexts: state.contexts, unavailable: state.unavailable }),
  useCan: () => true,
}));
vi.mock("@/hooks/use-account", () => ({ usePostLifecycle: () => ({ moveToTrash: vi.fn() }) }));

const [suspended, archived] = fixture.response.unavailable;
const renderList = () =>
  render(
    <MemoryRouter>
      <MyPostsList posts={[]} isLoading={false} isError={false} onRetry={() => {}} />
    </MemoryRouter>,
  );

describe("MyPostsList : état vide avec organisation indisponible (UX-SUSP 4.4)", () => {
  it("une organisation : phrase et lien vers son état, à la place de la phrase « sous une organisation »", () => {
    state.unavailable = [suspended];
    renderList();
    expect(screen.getByText(/Atelier Suspendu », qui n'est plus disponible pour le moment/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir Atelier Suspendu" })).toHaveAttribute("href", `/organizations/${suspended.id}`);
    expect(screen.queryByText(/se trouvent peut-être sous une organisation/)).not.toBeInTheDocument();
  });

  it("plusieurs organisations : lien vers Mes profils", () => {
    state.unavailable = [suspended, archived];
    renderList();
    expect(screen.getByRole("link", { name: "Voir mes organisations" })).toHaveAttribute("href", "/profiles");
  });

  it("aucune organisation indisponible : aucune phrase ajoutée", () => {
    state.unavailable = [];
    renderList();
    expect(screen.queryByText(/n'est plus disponible/)).not.toBeInTheDocument();
  });
});
