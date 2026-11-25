import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { OrganizationInvitation } from "@/api/types";
import { InvitationsPanel } from "./InvitationsPanel";
import { InviteDialog } from "./InviteDialog";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

beforeAll(async () => {
  configure({ asyncUtilTimeout: 5000 });
  await import("./RevokeInvitationDialog");
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const ORG = "11111111-1111-4111-8111-111111111111";
const TOKEN = "tok_ABC-123_secretsecretsecretsecretsecret00";
const LINK = `${window.location.origin}/organization-invitation#token=${TOKEN}`;
const INV1 = "44444444-4444-4444-8444-444444444441";
const INV2 = "44444444-4444-4444-8444-444444444442";
const INV3 = "44444444-4444-4444-8444-444444444443";

const apiError = (status: number, code?: string, data: Record<string, unknown> = {}, headers: Record<string, string> = {}) => ({
  response: { status, data: code ? { detail: "Message du serveur", code } : data, headers },
});
const NETWORK = { isAxiosError: true, message: "Network Error" };

const inv = (id: string, extra: Partial<OrganizationInvitation> = {}): OrganizationInvitation => ({
  invitation_id: id,
  role: "EDITOR",
  status: "PENDING",
  label: "Jean, comptable",
  created_at: "2026-11-09T08:00:00Z",
  expires_at: "2099-11-16T08:00:00Z",
  created_by_display_name: "Paul M.",
  is_mine: false,
  ...extra,
});
const page = (results: OrganizationInvitation[], next: string | null = null) => ({ data: { count: results.length, next, previous: null, results } });

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrap = (node: React.ReactNode, client = newClient()) => render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);

beforeEach(() => {
  online.value = true;
  window.innerWidth = 1024;
  sessionStorage.clear();
  localStorage.clear();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.info).mockClear();
});
afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "share", { value: undefined, configurable: true });
  Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
});

// ---------------------------------------------------------------------------------------------------------------------
describe("InviteDialog (E6a)", () => {
  const renderDialog = (limits: unknown = { invitation_ttl_days: 7 }) => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: limits });
    const onClose = vi.fn();
    const onAnnounce = vi.fn();
    wrap(<InviteDialog orgId={ORG} orgName="Boutique Lumière" online onClose={onClose} onAnnounce={onAnnounce} />);
    return { onClose, onAnnounce };
  };
  const choose = (name: RegExp) => fireEvent.click(within(screen.getByRole("dialog")).getByRole("radio", { name }));
  const submit = () => fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Créer le lien" }));
  const createdBody = { invitation_id: INV1, role: "EDITOR", status: "PENDING", label: "", created_at: "x", expires_at: "2026-11-16T08:00:00Z", link_token: TOKEN };

  it("étape 1 : Éditeur et Analyste seulement, aucun rôle présélectionné, bouton désactivé, aucun champ de coordonnées", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Inviter une personne" });
    const radios = within(dialog).getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(within(dialog).getByRole("radio", { name: /Éditeur/ })).not.toBeChecked();
    expect(within(dialog).getByRole("radio", { name: /Analyste/ })).not.toBeChecked();
    expect(within(dialog).queryByRole("radio", { name: /Propriétaire|Administrateur/ })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Créer le lien" })).toBeDisabled();
    expect(within(dialog).getByText(/Pour donner le rôle Administrateur ou Propriétaire/)).toBeInTheDocument();
    // Aucune recherche de compte : ni téléphone, ni e-mail, ni identifiant
    expect(within(dialog).queryByLabelText(/téléphone|e-mail|identifiant/i)).not.toBeInTheDocument();
    expect(within(dialog).getAllByRole("textbox")).toHaveLength(1);
  });

  it("étiquette : 60 caractères au plus, compteur, texte d'aide qui interdit les coordonnées", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    const field = within(dialog).getByLabelText("Étiquette (facultatif)");
    expect(field).toHaveAttribute("maxlength", "60");
    expect(within(dialog).getByText(/Ne mettez ni téléphone ni adresse/)).toBeInTheDocument();
    expect(within(dialog).getByText("0/60")).toBeInTheDocument();
    fireEvent.change(field, { target: { value: "Jean" } });
    expect(within(dialog).getByText("4/60")).toBeInTheDocument();
    expect(field.closest("[aria-live]")).toBeNull();
  });

  it("durée de validité lue de limits/ ; omise si le serveur ne la renvoie pas", async () => {
    const { unmount } = render(<div />);
    unmount();
    renderDialog({ invitation_ttl_days: 7 });
    expect(await screen.findByText("Le lien est valable 7 jours.")).toBeInTheDocument();
  });

  it("durée de validité absente : aucune phrase de validité", async () => {
    renderDialog({ max_categories_per_context: 3 });
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
    expect(within(dialog).queryByText(/Le lien est valable/)).not.toBeInTheDocument();
  });

  it("création : corps { role } sans étiquette vide ; étiquette envoyée sans espaces de bord", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: createdBody });
    renderDialog();
    await screen.findByRole("dialog");
    choose(/Analyste/);
    submit();
    await waitFor(() => expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/`, { role: "ANALYST" }));
  });

  it("création : l'étiquette saisie est envoyée telle quelle (rognée)", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: createdBody });
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    choose(/Éditeur/);
    fireEvent.change(within(dialog).getByLabelText("Étiquette (facultatif)"), { target: { value: "  Jean, comptable  " } });
    submit();
    await waitFor(() => expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/`, { role: "EDITOR", label: "Jean, comptable" }));
  });

  it("étape 2 : lien dans le fragment, avertissement, résumé, non fermable par clic extérieur, « Terminer » supprime le jeton", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: createdBody });
    const { onClose } = renderDialog();
    await screen.findByRole("dialog");
    choose(/Éditeur/);
    submit();
    const link = await screen.findByLabelText("Lien d'invitation");
    expect(link).toHaveValue(LINK);
    expect(link).toHaveAttribute("readonly");
    const dialog = screen.getByRole("dialog", { name: "Votre lien d'invitation" });
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/ne sera plus affichable après la fermeture.*rôle Éditeur/);
    expect(within(dialog).getByText(/Rôle : Éditeur\. Expire le 16 novembre 2026\./)).toBeInTheDocument();
    expect(within(dialog).getByText("Vous n'avez pas encore copié le lien.")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Partager" })).not.toBeInTheDocument();

    // Clic extérieur : la fenêtre reste ouverte
    fireEvent.pointerDown(document.body);
    fireEvent.click(document.body);
    expect(screen.getByLabelText("Lien d'invitation")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Terminer" }));
    expect(onClose).toHaveBeenCalledWith(true);
  });

  it("le jeton n'est ni dans un stockage, ni dans un toast, ni dans la console, ni dans l'URL", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: createdBody });
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => undefined));
    renderDialog();
    await screen.findByRole("dialog");
    choose(/Éditeur/);
    submit();
    await screen.findByLabelText("Lien d'invitation");
    expect(JSON.stringify({ ...localStorage })).not.toContain(TOKEN);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(TOKEN);
    expect(window.location.href).not.toContain(TOKEN);
    expect(JSON.stringify([vi.mocked(toast.success).mock.calls, vi.mocked(toast.error).mock.calls, vi.mocked(toast.info).mock.calls])).not.toContain(TOKEN);
    for (const spy of spies) expect(JSON.stringify(spy.mock.calls)).not.toContain(TOKEN);
    // Une seule occurrence visible : la valeur du champ (jamais un attribut, une région aria-live ni du texte)
    expect(document.querySelectorAll("[aria-live]")).toHaveLength(0);
    expect(document.body.textContent).not.toContain(TOKEN);
    expect(Array.from(document.querySelectorAll("*")).filter((el) => Array.from(el.attributes).some((a) => a.value.includes(TOKEN) && a.name !== "value"))).toHaveLength(0);
  });

  it("« Copier le lien » : presse-papiers, libellé « Lien copié », annonce sans le lien, rappel retiré", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: createdBody });
    const { onAnnounce } = renderDialog();
    await screen.findByRole("dialog");
    choose(/Éditeur/);
    submit();
    fireEvent.click(await screen.findByRole("button", { name: "Copier le lien" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LINK));
    expect(await screen.findByRole("button", { name: "Lien copié" })).toBeInTheDocument();
    expect(onAnnounce).toHaveBeenCalledWith("Lien copié");
    expect(JSON.stringify(onAnnounce.mock.calls)).not.toContain(TOKEN);
    expect(screen.queryByText("Vous n'avez pas encore copié le lien.")).not.toBeInTheDocument();
  });

  it("sans presse-papiers : repli execCommand ; si cela échoue aussi, message d'aide", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    const exec = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true);
    (document as unknown as { execCommand: unknown }).execCommand = exec;
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: createdBody });
    renderDialog();
    await screen.findByRole("dialog");
    choose(/Éditeur/);
    submit();
    const button = await screen.findByRole("button", { name: "Copier le lien" });
    fireEvent.click(button);
    expect(await screen.findByText("Copie impossible. Appuyez longuement sur le lien pour le copier.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copier le lien" }));
    expect(await screen.findByRole("button", { name: "Lien copié" })).toBeInTheDocument();
    expect(exec).toHaveBeenCalledWith("copy");
  });

  it("« Partager » seulement si navigator.share existe ; l'annulation n'est pas une erreur", async () => {
    const abort = Object.assign(new Error("annulé"), { name: "AbortError" });
    const share = vi.fn().mockRejectedValue(abort);
    Object.defineProperty(navigator, "share", { value: share, configurable: true });
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: createdBody });
    renderDialog();
    await screen.findByRole("dialog");
    choose(/Éditeur/);
    submit();
    fireEvent.click(await screen.findByRole("button", { name: "Partager" }));
    await waitFor(() =>
      expect(share).toHaveBeenCalledWith(
        expect.objectContaining({ url: LINK, title: "Invitation à rejoindre une équipe sur Connecte+", text: expect.stringContaining("Boutique Lumière") }),
      ),
    );
    expect(screen.queryByText(/Copie impossible/)).not.toBeInTheDocument();
  });

  describe("erreurs de création : valeurs conservées, fenêtre ouverte", () => {
    const attempt = async (error: unknown) => {
      const post = vi.spyOn(apiClient, "post").mockRejectedValue(error);
      const view = renderDialog();
      const dialog = await screen.findByRole("dialog");
      choose(/Analyste/);
      fireEvent.change(within(dialog).getByLabelText("Étiquette (facultatif)"), { target: { value: "Awa" } });
      submit();
      await waitFor(() => expect(post).toHaveBeenCalled());
      return { dialog, post, ...view };
    };

    it("409 invitation_limit_reached", async () => {
      const { dialog } = await attempt(apiError(409, "invitation_limit_reached"));
      expect(await within(dialog).findByText(/nombre maximal d'invitations en attente est atteint/)).toBeInTheDocument();
      expect(within(dialog).getByRole("radio", { name: /Analyste/ })).toBeChecked();
      expect(within(dialog).getByLabelText("Étiquette (facultatif)")).toHaveValue("Awa");
    });

    it("429 : message avec délai, bouton désactivé, aucune relance", async () => {
      const { dialog, post } = await attempt(apiError(429, undefined, {}, { "retry-after": "600" }));
      expect(await within(dialog).findByText(/Vous avez créé beaucoup d'invitations\. Réessayez dans 10 min\./)).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Créer le lien" })).toBeDisabled();
      expect(post).toHaveBeenCalledTimes(1);
    });

    it("400 {label} : message sous le champ", async () => {
      const { dialog } = await attempt(apiError(400, undefined, { label: ["Étiquette refusée."] }));
      const field = within(dialog).getByLabelText("Étiquette (facultatif)");
      expect(await within(dialog).findByText("Étiquette refusée.")).toBeInTheDocument();
      expect(field).toHaveAttribute("aria-invalid", "true");
    });

    it("400 {role} et invitation_role_not_allowed : message sous les rôles", async () => {
      const { dialog } = await attempt(apiError(400, "invitation_role_not_allowed"));
      expect(await within(dialog).findByText("Ce rôle ne peut pas être donné par invitation.")).toBeInTheDocument();
    });

    it("403 DENY_PERMISSION : fermeture avec le texte de refus", async () => {
      const { onClose } = await attempt(apiError(403, "DENY_PERMISSION"));
      await waitFor(() => expect(onClose).toHaveBeenCalledWith(false));
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Votre rôle ne permet pas cette action"));
    });

    it("403 DENY_SECURITY : texte existant dans la fenêtre", async () => {
      const { dialog } = await attempt(apiError(403, "DENY_SECURITY"));
      expect(await within(dialog).findByText(/temporairement impossible/)).toBeInTheDocument();
    });

    it("réseau coupé : message qui renvoie à l'onglet Invitations, aucune relance automatique", async () => {
      const { dialog, post } = await attempt(NETWORK);
      expect(await within(dialog).findByText("Connexion perdue. Vérifiez l'onglet Invitations avant de réessayer.")).toBeInTheDocument();
      expect(post).toHaveBeenCalledTimes(1);
      expect(within(dialog).getByRole("button", { name: "Créer le lien" })).toBeEnabled();
    });
  });

  it("hors ligne : « Créer le lien » désactivé avec la raison", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: {} });
    wrap(<InviteDialog orgId={ORG} orgName="Boutique Lumière" online={false} onClose={vi.fn()} onAnnounce={vi.fn()} />);
    const dialog = await screen.findByRole("dialog");
    choose(/Éditeur/);
    expect(within(dialog).getByRole("button", { name: "Créer le lien" })).toBeDisabled();
    expect(within(dialog).getByText("Reconnectez-vous pour effectuer cette action.")).toBeInTheDocument();
  });

  it("anti-doublon : le bouton est désactivé pendant l'appel", async () => {
    let release: (value: unknown) => void = () => undefined;
    const post = vi.spyOn(apiClient, "post").mockReturnValue(new Promise((resolve) => (release = resolve)) as never);
    renderDialog();
    await screen.findByRole("dialog");
    choose(/Éditeur/);
    submit();
    await waitFor(() => expect(screen.getByRole("button", { name: "Créer le lien" })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Créer le lien" }));
    expect(post).toHaveBeenCalledTimes(1);
    release({ data: createdBody });
    await screen.findByLabelText("Lien d'invitation");
  });
});

// ---------------------------------------------------------------------------------------------------------------------
describe("InvitationsPanel (onglet Invitations)", () => {
  const MANAGE = ["org.view_internal", "org.manage_members"];
  const renderPanel = (client = newClient()) => {
    const onAnnounce = vi.fn();
    const onInvite = vi.fn();
    const view = wrap(<InvitationsPanel org={{ id: ORG, capabilities: MANAGE }} onAnnounce={onAnnounce} onInvite={onInvite} />, client);
    return { ...view, onAnnounce, onInvite, client };
  };

  it("chargement : squelettes (aria-busy), puis la liste ; requête GET status=PENDING", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(page([inv(INV1)]));
    renderPanel();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(await screen.findByText("Jean, comptable")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/`, { params: { status: "PENDING" } });
    expect(screen.getByText(/Un lien ne peut pas être affiché une seconde fois/)).toBeInTheDocument();
  });

  it("tableau (ordinateur) : en-têtes, rôle, étiquette ou « Sans étiquette », créateur, « Créée par vous », échéance", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(
      page([inv(INV1), inv(INV2, { label: "", is_mine: true, role: "ANALYST" })]),
    );
    renderPanel();
    const table = await screen.findByRole("table", { name: "Invitations en attente" });
    for (const name of ["Rôle", "Étiquette", "Créée par", "Expire le"]) expect(within(table).getByRole("columnheader", { name })).toBeInTheDocument();
    expect(within(table).getByText("Créée par Paul M.")).toBeInTheDocument();
    expect(within(table).getByText("Créée par vous")).toBeInTheDocument();
    expect(within(table).getByText("Sans étiquette")).toBeInTheDocument();
    expect(within(table).getAllByText("16 novembre 2099").length).toBe(2);
  });

  it("mobile : cartes empilées avec « Expire le … »", async () => {
    window.innerWidth = 400;
    vi.spyOn(apiClient, "get").mockResolvedValue(page([inv(INV1)]));
    renderPanel();
    expect(await screen.findByText("Expire le 16 novembre 2099")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("une ligne expirée porte « Expirée » et n'a aucun bouton d'annulation", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(
      page([inv(INV1), inv(INV2, { status: "EXPIRED", label: "Vieille" }), inv(INV3, { expires_at: "2020-01-01T00:00:00Z", label: "Échue" })]),
    );
    renderPanel();
    await screen.findByText("Vieille");
    expect(screen.getAllByText("Expirée")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /^Annuler l'invitation/ })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Annuler l'invitation : Vieille" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Annuler l'invitation : Échue" })).not.toBeInTheDocument();
  });

  it("aucune donnée personnelle ni jeton : ni téléphone, ni e-mail, ni lien", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(page([inv(INV1)]));
    renderPanel();
    await screen.findByText("Jean, comptable");
    expect(document.body.textContent).not.toMatch(/@|\+243|token|organization-invitation/i);
  });

  it("vide : message et action « Inviter une personne »", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(page([]));
    const { onInvite } = renderPanel();
    expect(await screen.findByText("Aucune invitation en attente.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inviter une personne" }));
    expect(onInvite).toHaveBeenCalled();
  });

  it("erreur : message et « Réessayer » qui recharge", async () => {
    const get = vi.spyOn(apiClient, "get").mockRejectedValueOnce(apiError(429)).mockResolvedValue(page([inv(INV1)]));
    renderPanel();
    expect(await screen.findByText("Impossible de charger les invitations.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText("Jean, comptable")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("hors ligne : liste conservée, boutons désactivés, raison affichée", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(page([inv(INV1)]));
    online.value = false;
    renderPanel();
    const button = await screen.findByRole("button", { name: /^Annuler l'invitation/ });
    expect(button).toBeDisabled();
    expect(document.getElementById(button.getAttribute("aria-describedby") as string)).toHaveTextContent("Reconnectez-vous pour effectuer cette action.");
  });

  it("« Voir plus d'invitations » charge la page suivante", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce(page([inv(INV1)], "http://x/?page=2"))
      .mockResolvedValueOnce(page([inv(INV2, { label: "Suivante" })]));
    renderPanel();
    await screen.findByText("Jean, comptable");
    fireEvent.click(screen.getByRole("button", { name: "Voir plus d'invitations" }));
    expect(await screen.findByText("Suivante")).toBeInTheDocument();
    expect(get).toHaveBeenLastCalledWith(`accounts/organizations/${ORG}/invitations/`, { params: { status: "PENDING", page: 2 } });
  });

  describe("annuler une invitation (E6e)", () => {
    const open = async () => {
      const view = renderPanel();
      fireEvent.click(await screen.findByRole("button", { name: "Annuler l'invitation : Jean, comptable" }));
      const dialog = await screen.findByRole("alertdialog");
      return { dialog, ...view };
    };
    beforeEach(() => {
      vi.spyOn(apiClient, "get").mockResolvedValue(page([inv(INV1)]));
    });

    it("texte, boutons « Garder l'invitation » (focus initial) et « Annuler l'invitation »", async () => {
      const { dialog } = await open();
      expect(within(dialog).getByText("Annuler cette invitation ?")).toBeInTheDocument();
      expect(within(dialog).getByText(/Le lien ne fonctionnera plus/)).toBeInTheDocument();
      await waitFor(() => expect(within(dialog).getByRole("button", { name: "Garder l'invitation" })).toHaveFocus());
      expect(within(dialog).getByRole("button", { name: "Annuler l'invitation" })).toBeInTheDocument();
    });

    it("succès (204) : DELETE, toast, annonce, focus sur le titre de la liste", async () => {
      const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ status: 204, data: "" });
      const { dialog, onAnnounce } = await open();
      fireEvent.click(within(dialog).getByRole("button", { name: "Annuler l'invitation" }));
      await waitFor(() => expect(del).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/${INV1}/`));
      await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
      expect(toast.success).toHaveBeenCalledWith("Invitation annulée.");
      expect(onAnnounce).toHaveBeenCalledWith("Invitation annulée.");
      await waitFor(() => expect(screen.getByRole("heading", { name: "Invitations en attente" })).toHaveFocus());
    });

    it.each([
      ["409 invitation_not_pending", apiError(409, "invitation_not_pending")],
      ["404 invitation_not_found", apiError(404, "invitation_not_found")],
    ])("%s : information et rechargement", async (_label, error) => {
      vi.spyOn(apiClient, "delete").mockRejectedValue(error);
      const { dialog } = await open();
      fireEvent.click(within(dialog).getByRole("button", { name: "Annuler l'invitation" }));
      await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Cette invitation n'est plus en attente."));
      await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
      await waitFor(() => expect(vi.mocked(apiClient.get).mock.calls.length).toBeGreaterThan(1));
    });

    it("403 DENY_PERMISSION : fermeture avec le texte de refus", async () => {
      vi.spyOn(apiClient, "delete").mockRejectedValue(apiError(403, "DENY_PERMISSION"));
      const { dialog } = await open();
      fireEvent.click(within(dialog).getByRole("button", { name: "Annuler l'invitation" }));
      await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Votre rôle ne permet pas cette action"));
    });

    it("429 : message de patience et bouton désactivé ; réseau coupé : message de connexion, fenêtre ouverte", async () => {
      vi.spyOn(apiClient, "delete").mockRejectedValueOnce(apiError(429, undefined, {}, { "retry-after": "600" }));
      const { dialog } = await open();
      fireEvent.click(within(dialog).getByRole("button", { name: "Annuler l'invitation" }));
      expect(await within(dialog).findByText("Trop de tentatives. Réessayez dans quelques minutes.")).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Annuler l'invitation" })).toBeDisabled();
    });

    it("réseau coupé : message et fenêtre ouverte", async () => {
      vi.spyOn(apiClient, "delete").mockRejectedValue(NETWORK);
      const { dialog } = await open();
      fireEvent.click(within(dialog).getByRole("button", { name: "Annuler l'invitation" }));
      expect(await within(dialog).findByText("Connexion perdue. Réessayez quand vous êtes reconnecté.")).toBeInTheDocument();
      expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    });

    it("« Garder l'invitation » ferme sans appel et rend le focus au bouton de la ligne", async () => {
      const del = vi.spyOn(apiClient, "delete");
      const { dialog } = await open();
      fireEvent.click(within(dialog).getByRole("button", { name: "Garder l'invitation" }));
      await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
      expect(del).not.toHaveBeenCalled();
      await waitFor(() => expect(screen.getByRole("button", { name: "Annuler l'invitation : Jean, comptable" })).toHaveFocus());
    });
  });
});
