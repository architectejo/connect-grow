import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import fr from "@/i18n/locales/fr";
import fixture from "@/api/__fixtures__/contexts.json";
import type { OrganizationRole, UnavailableOrganization } from "@/api/types";
import { OrganizationUnavailableView } from "./OrganizationUnavailableView";

vi.mock("@/contexts/ActiveContextContext", () => ({ useActiveContext: () => ({ active: { type: "USER", id: "u" }, leaveActive: vi.fn(), switchToPersonal: vi.fn() }) }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const [suspendedFixture, archivedFixture] = fixture.response.unavailable as UnavailableOrganization[];
const ROLES: OrganizationRole[] = ["OWNER", "ADMIN", "EDITOR", "ANALYST"];
const STATUSES = ["SUSPENDED", "ARCHIVED"] as const;

const renderView = (org: UnavailableOrganization) =>
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <OrganizationUnavailableView org={org} />
      </QueryClientProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  online.value = true;
});
afterEach(() => vi.restoreAllMocks());

describe("OrganizationUnavailableView : 4 rôles x 2 statuts", () => {
  for (const status of STATUSES) {
    for (const role of ROLES) {
      it(`${status} / ${role} : textes du statut, recours selon le rôle, seule action « Quitter »`, () => {
        const base = status === "SUSPENDED" ? suspendedFixture : archivedFixture;
        renderView({ ...base, status, role });

        const u = fr.org.unavailable;
        expect(screen.getByText(u.title[status])).toBeInTheDocument();
        expect(screen.getByText(u.body[status])).toBeInTheDocument();
        expect(screen.getByText(u.recourse[status][role === "OWNER" ? "OWNER" : "other"])).toBeInTheDocument();
        // le recours de l'autre famille de rôles n'est pas affiché
        expect(screen.queryByText(u.recourse[status][role === "OWNER" ? "other" : "OWNER"])).not.toBeInTheDocument();
        expect(screen.getByLabelText(`Statut de l'organisation : ${fr.org.status[status]}`)).toBeInTheDocument();
        expect(screen.getByText(fr.role[role])).toBeInTheDocument();
        expect(screen.getByText(u.blockedTitle)).toBeInTheDocument();

        // seul « quitter l'organisation » est possible
        const buttons = screen.getAllByRole("button");
        expect(buttons).toHaveLength(1);
        expect(buttons[0]).toHaveTextContent("Quitter l'organisation");
        expect(buttons[0]).toBeEnabled();
        for (const hidden of ["Agir sous ce profil", "Voir le profil public", "Modifier le profil", "Envoyer les pièces", "Archiver l'organisation"]) {
          expect(screen.queryByText(hidden)).not.toBeInTheDocument();
        }
        expect(screen.queryByRole("link")).not.toBeInTheDocument();
        expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
      });
    }
  }

  it("annonce le statut poliment (role=status), jamais role=alert", () => {
    renderView(suspendedFixture);
    expect(screen.getByRole("status")).toHaveTextContent(fr.org.unavailable.title.SUSPENDED);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("organisation convertie : ajoute la phrase sur l'ancien compte entreprise", () => {
    renderView({ ...suspendedFixture, migrated_from_business: true });
    expect(screen.getByText(fr.org.unavailable.migrated)).toBeInTheDocument();
    renderView({ ...archivedFixture, migrated_from_business: false });
    expect(screen.getAllByText(fr.org.unavailable.migrated)).toHaveLength(1);
  });

  it("aucune donnée sensible ni mention de vérification dans les textes affichés", () => {
    for (const status of STATUSES) {
      const { container, unmount } = renderView({ ...suspendedFixture, status, role: "OWNER" });
      const text = container.textContent ?? "";
      expect(text).not.toMatch(/vérifié|motif|raison|NIF|sanction|membre/i);
      unmount();
    }
  });

  it("hors ligne : « Quitter » désactivé avec la raison", () => {
    online.value = false;
    renderView(suspendedFixture);
    const button = screen.getByRole("button", { name: "Quitter l'organisation" });
    expect(button).toBeDisabled();
    expect(screen.getByText(fr.common.offlineAction)).toBeInTheDocument();
  });

  it("sans la capacité org.leave : aucun bouton (le front lit les capacités du serveur)", () => {
    renderView({ ...suspendedFixture, capabilities: [] });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("le titre du document porte le nom et le statut", () => {
    renderView(archivedFixture);
    expect(document.title).toBe(`${archivedFixture.name} · Archivée`);
  });
});
