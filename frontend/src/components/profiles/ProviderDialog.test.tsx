import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { ProviderProfile } from "@/api/types";
import { ProviderDialog } from "./ProviderDialog";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));

const PROFILE: ProviderProfile = {
  id: "p1",
  display_name: "Marie couture",
  bio: "Couture",
  category_ids: [],
  status: "ACTIVE",
  created_at: "2026-10-10T10:00:00Z",
};

const renderDialog = (props: Partial<React.ComponentProps<typeof ProviderDialog>> = {}) => {
  const onOpenChange = vi.fn();
  const onDone = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <ProviderDialog open onOpenChange={onOpenChange} accountName="Marie Kabongo" onDone={onDone} {...props} />
    </QueryClientProvider>,
  );
  return { onOpenChange, onDone };
};

beforeEach(() => {
  online.value = true;
  vi.spyOn(apiClient, "get").mockImplementation((async (url: string) => {
    if (url.includes("limits")) return { data: { max_categories_per_context: 5, max_organizations_per_account: 10, name_min_length: 2, name_max_length: 255, description_max_length: 2000 } };
    if (url.includes("categories")) return { data: [{ id: "c1", name: "Mode", slug: "mode" }] };
    return { data: [] };
  }) as never);
});
afterEach(() => vi.restoreAllMocks());

describe("Activer le profil prestataire (E8)", () => {
  it("le nom affiché PUBLIC est pré-rempli avec le nom du compte et le dit", async () => {
    renderDialog();
    expect(await screen.findByLabelText("Nom affiché")).toHaveValue("Marie Kabongo");
    expect(screen.getByText("Ce nom est public. Il apparaît sur vos offres et votre profil prestataire.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activer le profil" })).toBeInTheDocument();
  });

  it("l'utilisateur peut changer le nom avant publication : c'est ce nom qui part au serveur", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ status: 201, data: PROFILE });
    const { onDone, onOpenChange } = renderDialog();
    fireEvent.change(await screen.findByLabelText("Nom affiché"), { target: { value: "Marie couture" } });
    fireEvent.click(screen.getByRole("button", { name: "Activer le profil" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(PROFILE, true));
    expect(post).toHaveBeenCalledWith("accounts/provider/activate/", { display_name: "Marie couture", bio: "", category_ids: [] });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("nom trop court : message, rien n'est envoyé", async () => {
    const post = vi.spyOn(apiClient, "post");
    renderDialog();
    fireEvent.change(await screen.findByLabelText("Nom affiché"), { target: { value: "M" } });
    fireEvent.click(screen.getByRole("button", { name: "Activer le profil" }));
    expect(await screen.findByText("Saisissez au moins 2 caractères.")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("compte restreint (DENY_SECURITY) : message de limitation, la fenêtre reste ouverte", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "DENY_SECURITY" } } });
    const { onOpenChange } = renderDialog();
    await screen.findByLabelText("Nom affiché");
    fireEvent.click(screen.getByRole("button", { name: "Activer le profil" }));
    expect(await screen.findByText(/temporairement impossible/)).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("modification d'un profil actif : valeurs actuelles, PATCH", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: { ...PROFILE, bio: "Retouches" } });
    renderDialog({ profile: PROFILE });
    expect(await screen.findByLabelText("Nom affiché")).toHaveValue("Marie couture");
    fireEvent.change(screen.getByLabelText("Présentation (facultatif)"), { target: { value: "Retouches" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("accounts/provider/", { display_name: "Marie couture", bio: "Retouches", category_ids: [] }));
  });

  it("profil désactivé (DENY_OBJECT_STATE) : propose de le réactiver", async () => {
    vi.spyOn(apiClient, "patch").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "DENY_OBJECT_STATE" } } });
    renderDialog({ profile: PROFILE });
    await screen.findByLabelText("Nom affiché");
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Votre profil prestataire est désactivé. Réactivez-le pour le modifier.")).toBeInTheDocument();
  });

  it("hors ligne : envoi désactivé avec la raison", async () => {
    online.value = false;
    renderDialog();
    expect(await screen.findByRole("button", { name: "Activer le profil" })).toBeDisabled();
    expect(screen.getByText("Reconnectez-vous pour effectuer cette action.")).toBeInTheDocument();
  });
});
