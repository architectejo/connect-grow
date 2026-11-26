import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { MyAwaitingInvitation } from "@/api/types";
import { AwaitingMembershipsSection } from "./AwaitingMembershipsSection";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

vi.setConfig({ testTimeout: 20_000 });

beforeAll(async () => {
  configure({ asyncUtilTimeout: 5000 });
  await import("./NewConfirmationCodeDialog");
  await import("./WithdrawAwaitingDialog");
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const SENTINEL = "482913";
const INV1 = "44444444-4444-4444-8444-444444444441";
const INV2 = "44444444-4444-4444-8444-444444444442";
const item = (id: string, extra: Partial<MyAwaitingInvitation> = {}): MyAwaitingInvitation => ({
  invitation_id: id,
  organization_name: "Boutique Lumière",
  org_type: "ENTREPRISE",
  role: "ADMIN",
  scope: { type: "ORGANIZATION", id: null },
  accepted_at: "2026-11-25T13:05:00Z",
  confirmation_expires_at: "2026-11-28T13:05:00Z",
  status: "AWAITING_CONFIRMATION",
  ...extra,
});
const apiError = (status: number, code?: string) => ({ isAxiosError: true, response: { status, data: code ? { detail: "Message du serveur", code } : {}, headers: {} } });
const NETWORK = { isAxiosError: true, message: "Network Error" };

let client: QueryClient;
const renderSection = (results: MyAwaitingInvitation[] | "error" = [item(INV1)]) => {
  const get = vi.spyOn(apiClient, "get").mockImplementation(async () => {
    if (results === "error") throw apiError(500);
    return { data: { count: results.length, next: null, previous: null, results } };
  });
  const onAnnounce = vi.fn();
  const onFocusFallback = vi.fn();
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AwaitingMembershipsSection onAnnounce={onAnnounce} onFocusFallback={onFocusFallback} />
    </QueryClientProvider>,
  );
  return { get, onAnnounce, onFocusFallback };
};

beforeEach(() => {
  online.value = true;
  window.innerWidth = 1024;
  sessionStorage.clear();
  localStorage.clear();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.info).mockClear();
});
afterEach(() => vi.restoreAllMocks());

describe("E17 : demandes en attente de confirmation (spec D2 §11)", () => {
  it("carte en attente : organisation, rôle, périmètre, dates, rappel « code non réaffiché », deux boutons nommés ; requête page_size=10", async () => {
    const { get } = renderSection();
    expect(await screen.findByRole("heading", { level: 2, name: "Demandes en attente de confirmation" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("accounts/organization-invitations/awaiting/", { params: { page_size: 10 } });
    expect(screen.getByRole("heading", { level: 3, name: "Boutique Lumière" })).toBeInTheDocument();
    expect(screen.getByText("Administrateur")).toBeInTheDocument();
    expect(screen.getByText("Toute l'organisation")).toBeInTheDocument();
    expect(screen.getByText(/^Acceptée le/)).toBeInTheDocument();
    expect(screen.getByText(/^Confirmation attendue avant le/)).toBeInTheDocument();
    expect(screen.getByText("Votre code n'est pas réaffiché ici. Si vous ne l'avez plus, obtenez-en un nouveau.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Obtenir un nouveau code pour Boutique Lumière" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Retirer ma demande pour Boutique Lumière" })).toBeEnabled();
  });

  it("demande échue : badge « Non confirmée à temps », aucun bouton", async () => {
    renderSection([item(INV1, { status: "EXPIRED" })]);
    expect(await screen.findByText("Non confirmée à temps")).toBeInTheDocument();
    expect(screen.getByText(/Demandez une nouvelle invitation/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("liste vide ou en erreur : section absente, aucune alerte", async () => {
    const { get } = renderSection([]);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Demandes en attente de confirmation" })).not.toBeInTheDocument();
    vi.restoreAllMocks();
    const failing = renderSection("error");
    await waitFor(() => expect(failing.get).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Demandes en attente de confirmation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("hors ligne : boutons désactivés avec la raison", async () => {
    online.value = false;
    renderSection();
    const button = await screen.findByRole("button", { name: "Obtenir un nouveau code pour Boutique Lumière" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Reconnectez-vous pour effectuer cette action.");
  });

  it("nouveau code : avertissement (focus « Garder mon code actuel »), puis code affiché, non fermable par clic extérieur ; annonce sans code", async () => {
    const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level));
    const { onAnnounce } = renderSection();
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { invitation_id: INV1, confirmation_code: SENTINEL, confirmation_expires_at: "2026-11-28T13:05:00Z" } });
    const trigger = await screen.findByRole("button", { name: "Obtenir un nouveau code pour Boutique Lumière" });
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "Obtenir un nouveau code ?" });
    expect(within(dialog).getByText(/L'ancien ne fonctionnera plus/)).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Garder mon code actuel" })).toHaveFocus());
    fireEvent.click(within(dialog).getByRole("button", { name: "Obtenir un nouveau code" }));
    const shown = await screen.findByRole("dialog", { name: "Votre nouveau code" });
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(`accounts/organization-invitations/${INV1}/confirmation-code/`);
    expect(within(shown).getByText("482 913")).toHaveAttribute("aria-hidden", "true");
    expect(within(shown).getByText("4 8 2 9 1 3")).toHaveClass("sr-only");
    await waitFor(() => expect(within(shown).getByRole("heading", { name: "Votre code de confirmation" })).toHaveFocus());
    expect(onAnnounce).toHaveBeenCalledWith("Nouveau code affiché à l'écran.");
    expect(within(shown).queryByRole("button", { name: /Copier|Partager/ })).not.toBeInTheDocument();
    // Le code ne vit que dans l'état du dialogue (même liste de canaux que AdminInvitations.test.tsx)
    const channels: Record<string, string> = {
      mutationCache: JSON.stringify(client.getMutationCache().getAll().map((m) => [m.state.variables, m.state.data])),
      queryCache: JSON.stringify(client.getQueryCache().getAll().map((q) => [q.queryKey, q.state.data])),
      storage: JSON.stringify({ ...sessionStorage, ...localStorage }),
      announce: JSON.stringify(onAnnounce.mock.calls),
      toasts: JSON.stringify([vi.mocked(toast.success).mock.calls, vi.mocked(toast.info).mock.calls, vi.mocked(toast.error).mock.calls]),
      liveRegions: Array.from(document.querySelectorAll("[aria-live], [role=status], [role=alert]"))
        .map((node) => node.textContent)
        .join("|"),
      attributes: Array.from(document.querySelectorAll("*"))
        .flatMap((node) => Array.from(node.attributes).map((a) => a.value))
        .join("|"),
      console: JSON.stringify(consoleSpies.map((spy) => spy.mock.calls)),
      url: window.location.href,
    };
    expect(Object.entries(channels).filter(([, value]) => value.includes(SENTINEL)).map(([name]) => name)).toEqual([]);
    fireEvent.click(within(shown).getByRole("button", { name: "J'ai noté le code" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.body.innerHTML).not.toContain("482 913");
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("nouveau code : « Garder mon code actuel » ferme sans appel", async () => {
    renderSection();
    const post = vi.spyOn(apiClient, "post");
    fireEvent.click(await screen.findByRole("button", { name: "Obtenir un nouveau code pour Boutique Lumière" }));
    const dialog = await screen.findByRole("dialog", { name: "Obtenir un nouveau code ?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Garder mon code actuel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(post).not.toHaveBeenCalled();
  });

  it("nouveau code, réseau coupé : texte dédié, AUCUNE relance automatique, nouvel essai manuel", async () => {
    renderSection();
    const post = vi.spyOn(apiClient, "post").mockRejectedValue(NETWORK);
    fireEvent.click(await screen.findByRole("button", { name: "Obtenir un nouveau code pour Boutique Lumière" }));
    const dialog = await screen.findByRole("dialog", { name: "Obtenir un nouveau code ?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Obtenir un nouveau code" }));
    expect(await within(dialog).findByText(/Un nouveau code a peut-être été créé/)).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
    fireEvent.click(within(dialog).getByRole("button", { name: "Obtenir un nouveau code" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  });

  it("nouveau code, 409 invitation_not_awaiting_confirmation : toast « n'est plus en attente », listes rechargées", async () => {
    const { get } = renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(409, "invitation_not_awaiting_confirmation"));
    fireEvent.click(await screen.findByRole("button", { name: "Obtenir un nouveau code pour Boutique Lumière" }));
    const dialog = await screen.findByRole("dialog", { name: "Obtenir un nouveau code ?" });
    const before = get.mock.calls.length;
    const invalidate = vi.spyOn(client, "invalidateQueries");
    fireEvent.click(within(dialog).getByRole("button", { name: "Obtenir un nouveau code" }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Cette invitation n'est plus en attente."));
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(before));
    // La demande a peut-être été confirmée : la liste des profils est aussi rechargée
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["contexts"] });
  });

  it("retrait : focus « Garder la demande », POST withdraw/, toast et annonce, focus repli si la section disparaît", async () => {
    const { onAnnounce, onFocusFallback } = renderSection();
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: "" });
    fireEvent.click(await screen.findByRole("button", { name: "Retirer ma demande pour Boutique Lumière" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Retirer votre demande pour « Boutique Lumière » ?" });
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Garder la demande" })).toHaveFocus());
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer ma demande" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith(`accounts/organization-invitations/${INV1}/withdraw/`));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Demande retirée."));
    expect(onAnnounce).toHaveBeenCalledWith("Demande retirée.");
    await waitFor(() => expect(onFocusFallback).toHaveBeenCalled());
  });

  it("dialogues hors ligne : bouton d'action désactivé, relié à la mention hors ligne", async () => {
    const { WithdrawAwaitingDialog } = await import("./WithdrawAwaitingDialog");
    const { NewConfirmationCodeDialog } = await import("./NewConfirmationCodeDialog");
    client = new QueryClient();
    const { unmount } = render(
      <QueryClientProvider client={client}>
        <WithdrawAwaitingDialog invitationId={INV1} organizationName="Boutique Lumière" online={false} onClose={vi.fn()} onWithdrawn={vi.fn()} onGone={vi.fn()} />
      </QueryClientProvider>,
    );
    const withdraw = within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Retirer ma demande" });
    expect(withdraw).toBeDisabled();
    expect(withdraw).toHaveAccessibleDescription("Reconnectez-vous pour effectuer cette action.");
    unmount();
    render(
      <QueryClientProvider client={client}>
        <NewConfirmationCodeDialog invitation={item(INV1)} online={false} onClose={vi.fn()} onGone={vi.fn()} onAnnounce={vi.fn()} />
      </QueryClientProvider>,
    );
    const request = within(await screen.findByRole("dialog")).getByRole("button", { name: "Obtenir un nouveau code" });
    expect(request).toBeDisabled();
    expect(request).toHaveAccessibleDescription("Reconnectez-vous pour effectuer cette action.");
  });

  it("retrait, 404 invitation_not_found : toast « n'est plus en attente »", async () => {
    renderSection([item(INV1), item(INV2, { organization_name: "ONG Espoir" })]);
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(404, "invitation_not_found"));
    fireEvent.click(await screen.findByRole("button", { name: "Retirer ma demande pour ONG Espoir" }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer ma demande" }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Cette invitation n'est plus en attente."));
  });
});
