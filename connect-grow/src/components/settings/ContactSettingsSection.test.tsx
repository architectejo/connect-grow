import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { ContactSettings } from "@/api/types";
import { ContactSettingsSection } from "./ContactSettingsSection";

// jsdom n'a pas ResizeObserver (requis par input-otp)
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ isAuthenticated: true, user: { phone: "+243812345678", phone_verified: true } }),
}));

// Profil actif : personnel par défaut, organisation dans les tests dédiés
const activeMock = vi.hoisted(() => ({
  active: { type: "USER", id: "u1", name: "Compte Test", role: null, orgType: null, photo: null, capabilities: [] as string[], confirmed: true },
}));
vi.mock("@/contexts/ActiveContextContext", () => ({ useActiveContext: () => ({ active: activeMock.active }) }));

const personalProfile = { type: "USER", id: "u1", name: "Compte Test", role: null, orgType: null, photo: null, capabilities: [], confirmed: true };
const organizationProfile = (capabilities: string[]) => ({
  type: "ORGANIZATION",
  id: "o1",
  name: "Atelier X",
  role: "ADMIN",
  orgType: "BOUTIQUE",
  photo: null,
  capabilities,
  confirmed: true,
});

const fixture = (over: Partial<ContactSettings> = {}): ContactSettings => ({
  context: { type: "USER", id: "u1" },
  available_channels: ["MESSAGE", "CALL", "WHATSAPP"],
  login_phone_masked: "+243 81 *** ** 45",
  can_use_login_phone: true,
  phone: { masked: "+243 81 *** ** 45", is_verified: true, login_phone_masked: "+243 81 *** ** 45", can_use_login_phone: true },
  channels: { MESSAGE: { enabled: true }, CALL: { enabled: false }, WHATSAPP: { enabled: false } },
  current_text_version: "2026-10-v1",
  ...over,
});

const renderSection = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return render(<ContactSettingsSection />, { wrapper: Wrapper });
};

describe("ContactSettingsSection", () => {
  beforeEach(() => {
    activeMock.active = personalProfile as typeof activeMock.active;
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: fixture() });
  });
  afterEach(() => vi.restoreAllMocks());

  it("par défaut : Message actif, Appel et WhatsApp désactivés ; numéro masqué", async () => {
    renderSection();
    expect(await screen.findByRole("switch", { name: "Message dans Connecte+" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Appel téléphonique" })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "WhatsApp" })).not.toBeChecked();
    expect(screen.getByTestId("contact-phone-masked")).toHaveTextContent("+243 81 *** ** 45");
  });

  it("sans numéro de contact : utilise le masque du numéro de connexion fourni par le serveur", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: fixture({ phone: null, login_phone_masked: "+243 99 *** ** 07", can_use_login_phone: true }),
    });
    renderSection();
    expect(await screen.findByText("Utiliser mon numéro de connexion (+243 99 *** ** 07)")).toBeInTheDocument();
    expect(screen.queryByText(/5678/)).not.toBeInTheDocument();
  });

  it("racine : can_use_login_phone faux désactive l'usage du numéro de connexion, même si le compte a un téléphone", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: fixture({ phone: null, login_phone_masked: "+243 99 *** ** 07", can_use_login_phone: false }),
    });
    renderSection();
    expect(await screen.findByText(/Vérifiez d'abord votre numéro de connexion/)).toBeInTheDocument();
  });

  it("Appel et WhatsApp restent verrouillés tant que le numéro n'est pas vérifié", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: fixture({ phone: { masked: "+243 81 *** ** 45", is_verified: false, login_phone_masked: "", can_use_login_phone: false } }),
    });
    renderSection();
    expect(await screen.findByRole("switch", { name: "Appel téléphonique" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "WhatsApp" })).toBeDisabled();
    expect(screen.getByText("Vérifier le numéro")).toBeInTheDocument();
  });

  it("activer Appel ouvre d'abord le dialogue, sans appel réseau avant acceptation", async () => {
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({
      data: fixture({ channels: { MESSAGE: { enabled: true }, CALL: { enabled: true, text_version: "2026-10-v1" }, WHATSAPP: { enabled: false } } }),
    });
    renderSection();
    fireEvent.click(await screen.findByRole("switch", { name: "Appel téléphonique" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/retirer votre accord/i)).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "J'accepte et j'active" }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("accounts/contact-settings/channels/CALL/", { enabled: true, text_version: "2026-10-v1" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("switch", { name: "Appel téléphonique" })).toBeChecked();
  });

  it("annuler le dialogue n'active rien", async () => {
    const put = vi.spyOn(apiClient, "put");
    renderSection();
    fireEvent.click(await screen.findByRole("switch", { name: "WhatsApp" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/WhatsApp \(Meta\)/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Annuler" }));
    expect(put).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: "WhatsApp" })).not.toBeChecked();
  });

  it("désactiver est immédiat, sans dialogue (révocation)", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: fixture({ channels: { MESSAGE: { enabled: true }, CALL: { enabled: true, text_version: "2026-10-v1" }, WHATSAPP: { enabled: false } } }),
    });
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: fixture() });
    renderSection();
    fireEvent.click(await screen.findByRole("switch", { name: "Appel téléphonique" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("accounts/contact-settings/channels/CALL/", { enabled: false }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("erreur consent_version_mismatch : message français, dialogue ouvert", async () => {
    vi.spyOn(apiClient, "put").mockRejectedValue({ response: { status: 400, data: { detail: "x", code: "consent_version_mismatch" } } });
    renderSection();
    fireEvent.click(await screen.findByRole("switch", { name: "Appel téléphonique" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "J'accepte et j'active" }));
    expect(await within(dialog).findByText("Le texte a changé, relisez-le avant d'accepter.")).toBeInTheDocument();
  });

  it("état d'erreur avec Réessayer, puis succès", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce({ response: { status: 500, data: {} } });
    renderSection();
    fireEvent.click(await screen.findByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("switch", { name: "Message dans Connecte+" })).toBeInTheDocument();
  });

  it("sans numéro de contact : propose le numéro de connexion masqué, sans le copier avant le geste", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: fixture({ phone: null }) });
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: fixture() });
    renderSection();
    const button = await screen.findByRole("button", { name: /Utiliser mon numéro de connexion/ });
    expect(button).toHaveTextContent("+243 81 *** ** 45");
    expect(button).not.toHaveTextContent("812345678");
    expect(put).not.toHaveBeenCalled();
    fireEvent.click(button);
    await waitFor(() => expect(put).toHaveBeenCalledWith("accounts/contact-settings/phone/", { use_login_phone: true }));
  });

  describe("profil actif : organisation", () => {
    const orgSettings = (over: Partial<ContactSettings> = {}) =>
      fixture({
        phone: null,
        context: { type: "ORGANIZATION", id: "o1" },
        available_channels: ["MESSAGE"],
        login_phone_masked: null,
        can_use_login_phone: false,
        ...over,
      });

    it("canal Message seul : ni appel, ni WhatsApp, ni numéro, et le texte explicite", async () => {
      activeMock.active = organizationProfile(["contact.manage_channels"]) as typeof activeMock.active;
      vi.mocked(apiClient.get).mockResolvedValue({ data: orgSettings() });
      renderSection();
      expect(await screen.findByRole("switch", { name: "Message dans Connecte+" })).toBeChecked();
      expect(screen.queryByRole("switch", { name: "Appel téléphonique" })).not.toBeInTheDocument();
      expect(screen.queryByRole("switch", { name: "WhatsApp" })).not.toBeInTheDocument();
      expect(screen.queryByText(/Utiliser mon numéro de connexion/)).not.toBeInTheDocument();
      expect(screen.getByText(/ne sont pas encore proposés pour les organisations/)).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Contact avec les acheteurs — Atelier X" })).toBeInTheDocument();
    });

    it("sans available_channels (réponse inattendue), seul le message est proposé", async () => {
      activeMock.active = organizationProfile(["contact.manage_channels"]) as typeof activeMock.active;
      vi.mocked(apiClient.get).mockResolvedValue({ data: orgSettings({ available_channels: undefined as never }) });
      renderSection();
      await screen.findByRole("switch", { name: "Message dans Connecte+" });
      expect(screen.queryByRole("switch", { name: "Appel téléphonique" })).not.toBeInTheDocument();
    });

    it("le numéro personnel du membre n'est jamais proposé quand le serveur ouvre les canaux téléphoniques", async () => {
      activeMock.active = organizationProfile(["contact.manage_channels"]) as typeof activeMock.active;
      vi.mocked(apiClient.get).mockResolvedValue({ data: orgSettings({ available_channels: ["MESSAGE", "CALL", "WHATSAPP"] }) });
      renderSection();
      expect(await screen.findByRole("switch", { name: "Appel téléphonique" })).toBeInTheDocument();
      expect(screen.queryByText(/Utiliser mon numéro de connexion/)).not.toBeInTheDocument();
    });

    it("canal devenu indisponible (channel_not_available) : message français, réglages rechargés, aucun consentement laissé ouvert", async () => {
      activeMock.active = organizationProfile(["contact.manage_channels"]) as typeof activeMock.active;
      const open = orgSettings({
        available_channels: ["MESSAGE", "CALL", "WHATSAPP"],
        phone: { masked: "+243 89 *** ** 11", is_verified: true, login_phone_masked: "", can_use_login_phone: false },
      });
      const get = vi.mocked(apiClient.get).mockResolvedValueOnce({ data: open }).mockResolvedValue({ data: orgSettings({ phone: open.phone }) });
      vi.spyOn(apiClient, "put").mockRejectedValue({
        response: { status: 400, data: { channel: ["x"], detail: "x", code: "channel_not_available" } },
      });
      renderSection();
      fireEvent.click(await screen.findByRole("switch", { name: "Appel téléphonique" }));
      fireEvent.click(await screen.findByRole("button", { name: "J'accepte et j'active" }));
      expect(await screen.findByText(/n'est pas proposé pour ce profil/)).toBeInTheDocument();
      await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(screen.queryByRole("switch", { name: "Appel téléphonique" })).not.toBeInTheDocument());
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("numéro de connexion refusé pour une organisation (login_phone_not_allowed) : message français dédié", async () => {
      activeMock.active = organizationProfile(["contact.manage_channels"]) as typeof activeMock.active;
      vi.mocked(apiClient.get).mockResolvedValue({ data: orgSettings({ available_channels: ["MESSAGE", "CALL", "WHATSAPP"] }) });
      vi.spyOn(apiClient, "put").mockRejectedValue({
        response: { status: 400, data: { detail: "x", code: "login_phone_not_allowed" } },
      });
      renderSection();
      await screen.findByRole("switch", { name: "Appel téléphonique" });
      fireEvent.change(screen.getByLabelText("Numéro de contact", { selector: "input" }), { target: { value: "891111111" } });
      fireEvent.click(screen.getByRole("button", { name: "Enregistrer et recevoir le code" }));
      expect(await screen.findByText(/ne peut pas servir de numéro à l'organisation/)).toBeInTheDocument();
    });

    it("organisation suspendue (403 DENY_SECURITY) : texte de refus français, bouton « Réessayer »", async () => {
      activeMock.active = organizationProfile(["contact.manage_channels"]) as typeof activeMock.active;
      vi.mocked(apiClient.get).mockRejectedValue({
        response: { status: 403, data: { detail: "Cette organisation est suspendue.", code: "DENY_SECURITY" } },
      });
      renderSection();
      expect(await screen.findByText(/temporairement impossible/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
    });

    it("éditeur ou analyste : accès refusé, aucune requête envoyée", async () => {
      activeMock.active = organizationProfile(["offer.view_internal", "stats.view"]) as typeof activeMock.active;
      const get = vi.mocked(apiClient.get);
      renderSection();
      expect(await screen.findByText("Seuls le propriétaire et les administrateurs gèrent les moyens de contact.")).toBeInTheDocument();
      expect(get).not.toHaveBeenCalled();
    });
  });
});
