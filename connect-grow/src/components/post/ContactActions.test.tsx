import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { ContactChannel, RevealedContact } from "@/api/types";
import { ContactActions } from "./ContactActions";

const auth = vi.hoisted(() => ({ isAuthenticated: true }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

const OFFER = "11111111-1111-4111-8111-111111111111";
const PHONE = "+243812345678";

const callResult: RevealedContact = {
  contact_event_id: "22222222-2222-4222-8222-222222222222",
  channel: "CALL",
  created: true,
  phone: PHONE,
  tel_url: `tel:${PHONE}`,
  whatsapp_url: null,
};
const whatsappResult: RevealedContact = {
  ...callResult,
  channel: "WHATSAPP",
  tel_url: null,
  whatsapp_url: "https://wa.me/243812345678?text=Chaussures",
};

const apiError = (status: number, code: string, headers: Record<string, string> = {}) =>
  Object.assign(new Error(code), { response: { status, data: { detail: "x", code }, headers } });

function renderActions(allowed: ContactChannel[], layout: "stack" | "bar" = "stack", onMessage = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[`/post/${OFFER}`]}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  const view = render(
    <ContactActions offerId={OFFER} sellerName="Marie" allowedChannels={allowed} layout={layout} onMessage={onMessage} />,
    { wrapper: Wrapper },
  );
  return { ...view, client, onMessage };
}

describe("ContactActions", () => {
  beforeEach(() => {
    auth.isAuthenticated = true;
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it.each(["stack", "bar"] as const)("n'affiche que les moyens autorisés, sans lien ni numéro (%s)", (layout) => {
    const { container } = renderActions(["MESSAGE", "WHATSAPP"], layout);
    expect(screen.queryByRole("button", { name: /Appeler/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /WhatsApp/ })).toBeInTheDocument();
    expect(container.querySelectorAll("a")).toHaveLength(0);
    expect(container.innerHTML).not.toMatch(/tel:|wa\.me|\+243/);
  });

  it("MESSAGE seul : ni Appeler ni WhatsApp ; sans MESSAGE, le bouton Message disparaît", () => {
    const { unmount } = renderActions(["MESSAGE"]);
    expect(screen.getByRole("button", { name: "Envoyer un message" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Appeler|WhatsApp/ })).not.toBeInTheDocument();
    unmount();
    renderActions(["CALL"]);
    expect(screen.queryByRole("button", { name: "Envoyer un message" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Appeler/ })).toBeInTheDocument();
  });

  it("aucun moyen autorisé : message explicatif, aucun bouton", () => {
    renderActions([]);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText(/n'accepte aucun moyen de contact/)).toBeInTheDocument();
  });

  it("le bouton Message appelle onMessage", () => {
    const { onMessage } = renderActions(["MESSAGE", "CALL"]);
    fireEvent.click(screen.getByRole("button", { name: "Envoyer un message" }));
    expect(onMessage).toHaveBeenCalledOnce();
  });

  it("le clic ouvre l'avis préalable sans appeler l'API ni afficher de numéro", () => {
    const post = vi.spyOn(apiClient, "post");
    renderActions(["CALL"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const notice = screen.getByText(/nom d'affichage abrégé/);
    expect(notice).toHaveTextContent(/« Marie K\. »/);
    expect(notice).toHaveTextContent(/l'annonce.*moyen de contact.*date/);
    expect(post).not.toHaveBeenCalled();
    expect(document.body.innerHTML).not.toMatch(/tel:|\+243/);
  });

  it("visiteur non connecté : invitation à se connecter, pas d'appel API", () => {
    auth.isAuthenticated = false;
    const post = vi.spyOn(apiClient, "post");
    renderActions(["WHATSAPP"]);
    fireEvent.click(screen.getByRole("button", { name: /WhatsApp/ }));
    expect(screen.getByText(/Connectez-vous pour voir le numéro/)).toBeInTheDocument();
    const login = screen.getByRole("link", { name: "Se connecter" });
    expect(login).toHaveAttribute("href", `/login?next=${encodeURIComponent(`/post/${OFFER}`)}`);
    expect(screen.queryByRole("button", { name: "Afficher le numéro" })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("Appeler : POST reveal puis numéro et lien tel: issus de la réponse", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: callResult });
    renderActions(["CALL"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("interactions/contacts/reveal/", { offer: OFFER, channel: "CALL" }));
    expect(await screen.findByTestId("revealed-phone")).toHaveTextContent(PHONE);
    const link = screen.getByRole("link", { name: "Appeler ce numéro" });
    expect(link).toHaveAttribute("href", `tel:${PHONE}`);
    await waitFor(() => expect(link).toHaveFocus());
  });

  it("WhatsApp : lien wa.me ouvert dans un nouvel onglet sécurisé", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: whatsappResult });
    renderActions(["WHATSAPP"]);
    fireEvent.click(screen.getByRole("button", { name: /WhatsApp/ }));
    fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
    const link = await screen.findByRole("link", { name: "Ouvrir WhatsApp" });
    expect(link).toHaveAttribute("href", whatsappResult.whatsapp_url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("refuse un lien inattendu venu du serveur (schéma javascript:)", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: { ...callResult, tel_url: "javascript:alert(1)" } });
    renderActions(["CALL"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
    expect(await screen.findByText(/n'a pas pu être affiché/)).toBeInTheDocument();
    expect(screen.queryByTestId("revealed-phone")).not.toBeInTheDocument();
    expect(document.querySelector("a[href^='javascript']")).toBeNull();
  });

  it("ne persiste rien : ni stockage du navigateur, ni cache React Query ; effacé à la fermeture", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: callResult });
    const { client } = renderActions(["CALL"]);
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
    await screen.findByTestId("revealed-phone");

    expect(JSON.stringify({ ...localStorage })).not.toContain("243");
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("243");
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.state.data))).not.toContain("243");

    fireEvent.click(screen.getByRole("button", { name: "Fermer" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.body.innerHTML).not.toContain("243812345678");
    // Après réouverture, le numéro n'est plus là : il faut redemander
    fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
    expect(screen.queryByTestId("revealed-phone")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Afficher le numéro" })).toBeInTheDocument();
  });

  describe("erreurs", () => {
    const open = (allowed: ContactChannel[] = ["MESSAGE", "CALL"]) => {
      const view = renderActions(allowed);
      fireEvent.click(screen.getByRole("button", { name: /Appeler/ }));
      fireEvent.click(screen.getByRole("button", { name: "Afficher le numéro" }));
      return view;
    };

    it.each([
      ["reveal_quota_account", 429, { "Retry-After": "7200" }, /beaucoup de numéros.*2 heures/],
      ["reveal_quota_new_account", 429, { "Retry-After": "90" }, /compte est récent.*2 minutes/],
      ["reveal_quota_ip", 429, { "Retry-After": "30" }, /depuis votre connexion.*30 secondes/],
      ["throttled", 429, { "Retry-After": "1" }, /Trop de demandes.*1 seconde/],
    ])("%s : délai tiré de Retry-After et repli par message", async (code, status, headers, text) => {
      vi.spyOn(apiClient, "post").mockRejectedValue(apiError(status, code, headers));
      const { onMessage } = open();
      expect(await screen.findByRole("alert")).toHaveTextContent(text);
      expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Écrire un message à la place" }));
      expect(onMessage).toHaveBeenCalledOnce();
    });

    it("429 sans Retry-After : « quelques instants »", async () => {
      vi.spyOn(apiClient, "post").mockRejectedValue(apiError(429, "reveal_quota_ip"));
      open();
      expect(await screen.findByRole("alert")).toHaveTextContent("quelques instants");
    });

    it.each([
      ["own_offer", 403, /propre annonce/],
      ["contact_restricted", 403, /ne peut pas contacter/],
      ["channel_not_allowed", 403, /n'accepte pas ce moyen/],
      ["offer_not_found", 404, /plus disponible/],
    ])("%s : message français", async (code, status, text) => {
      vi.spyOn(apiClient, "post").mockRejectedValue(apiError(status, code));
      open();
      expect(await screen.findByRole("alert")).toHaveTextContent(text);
      expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
    });

    it("reveal_in_progress (409) : délai et bouton Réessayer qui relance", async () => {
      const post = vi
        .spyOn(apiClient, "post")
        .mockRejectedValueOnce(apiError(409, "reveal_in_progress", { "Retry-After": "2" }))
        .mockResolvedValueOnce({ data: callResult });
      open();
      expect(await screen.findByRole("alert")).toHaveTextContent(/déjà en cours.*2 secondes/);
      fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
      expect(await screen.findByTestId("revealed-phone")).toHaveTextContent(PHONE);
      expect(post).toHaveBeenCalledTimes(2);
    });

    it("401 : invitation à se connecter", async () => {
      vi.spyOn(apiClient, "post").mockRejectedValue(apiError(401, "not_authenticated"));
      open();
      expect(await screen.findByText(/session a expiré/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Se connecter" })).toBeInTheDocument();
    });

    it("réseau coupé et erreur serveur : Réessayer", async () => {
      vi.spyOn(apiClient, "post").mockRejectedValue(new Error("Network Error"));
      const { unmount } = open();
      expect(await screen.findByRole("alert")).toHaveTextContent(/Connexion impossible/);
      expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
      unmount();
      vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 503, data: "<html>" } });
      open();
      expect(await screen.findByRole("alert")).toHaveTextContent(/rencontre un problème/);
      expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
    });

    it("channel_invalid (400) : message générique, sans Réessayer", async () => {
      vi.spyOn(apiClient, "post").mockRejectedValue(apiError(400, "channel_invalid"));
      open();
      expect(await screen.findByRole("alert")).toHaveTextContent(/n'a pas pu être affiché/);
      expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Afficher le numéro" })).not.toBeInTheDocument();
    });

    it("sans repli par message quand MESSAGE n'est pas autorisé", async () => {
      vi.spyOn(apiClient, "post").mockRejectedValue(apiError(429, "reveal_quota_ip", { "Retry-After": "30" }));
      open(["CALL"]);
      await screen.findByRole("alert");
      expect(screen.queryByRole("button", { name: "Écrire un message à la place" })).not.toBeInTheDocument();
    });
  });
});
