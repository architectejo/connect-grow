import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { AwaitingConfirmationInvitation } from "@/api/types";
import { TeamPendingActions } from "./TeamPendingActions";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true, user: { id: "compte-A", phone: "+243810000047", email: null } }) }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// jsdom + Radix + dialogues chargés à la demande : délai propre à ce fichier
vi.setConfig({ testTimeout: 20_000 });

beforeAll(async () => {
  configure({ asyncUtilTimeout: 5000 });
  await import("./ConfirmAdminInvitationDialog");
  await import("./RejectAdminInvitationDialog");
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

/** Valeur sentinelle du code de rattachement : elle ne doit apparaître dans aucun canal hors du champ de saisie. */
const SENTINEL = "482913";
const ORG = "11111111-1111-4111-8111-111111111111";
const INV1 = "44444444-4444-4444-8444-444444444441";
const INV2 = "44444444-4444-4444-8444-444444444442";
const PASSWORD = "mot-de-passe-secret";

const awaiting = (id: string, extra: Partial<AwaitingConfirmationInvitation> = {}): AwaitingConfirmationInvitation => ({
  invitation_id: id,
  role: "ADMIN",
  status: "AWAITING_CONFIRMATION",
  label: "",
  created_at: "2026-11-20T08:00:00Z",
  expires_at: "2026-11-27T08:00:00Z",
  created_by_display_name: "Paul M.",
  is_mine: true,
  scope: { type: "ORGANIZATION", id: null },
  requires_confirmation: true,
  accepted_at: "2026-11-25T13:05:00Z",
  confirmation_expires_at: "2026-11-28T13:05:00Z",
  accepted_by_display_name: "Marie K.",
  accepted_by_phone_hint: "••47",
  can_confirm: true,
  inviter_has_authority: true,
  ...extra,
});
const apiError = (status: number, code?: string, headers: Record<string, string> = {}) => ({
  isAxiosError: true,
  response: { status, data: code ? { detail: "Message du serveur", code } : {}, headers },
});
const NETWORK = { isAxiosError: true, message: "Network Error" };

let client: QueryClient;
const ORG_FULL = { id: ORG, name: "Boutique Lumière", capabilities: ["org.manage_members", "org.view_internal"] };

const renderSection = (results: AwaitingConfirmationInvitation[] | Error = [awaiting(INV1)], org = ORG_FULL) => {
  const get = vi.spyOn(apiClient, "get").mockImplementation(async () => {
    if (results instanceof Error) throw apiError(500);
    return { data: { count: results.length, next: null, previous: null, results } };
  });
  const onAnnounce = vi.fn();
  const onFocusFallback = vi.fn();
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TeamPendingActions org={org} onAnnounce={onAnnounce} onFocusFallback={onFocusFallback} />
    </QueryClientProvider>,
  );
  return { get, onAnnounce, onFocusFallback };
};

const openConfirm = async (name = "Marie K.") => {
  fireEvent.click(await screen.findByRole("button", { name: `Confirmer l'accès de ${name}` }));
  return screen.findByRole("dialog", { name: `Confirmer l'accès de ${name}` });
};
const codeField = (dialog: HTMLElement) => within(dialog).getByLabelText("Code à 6 chiffres") as HTMLInputElement;
const passwordField = (dialog: HTMLElement) => within(dialog).getByLabelText("Votre mot de passe") as HTMLInputElement;
const fillAll = (dialog: HTMLElement, code = "482 913") => {
  fireEvent.change(codeField(dialog), { target: { value: code } });
  fireEvent.click(within(dialog).getByRole("checkbox"));
  fireEvent.change(passwordField(dialog), { target: { value: PASSWORD } });
};
const submitButton = (dialog: HTMLElement) => within(dialog).getByRole("button", { name: "Confirmer l'accès" });

/** Tous les canaux où le code ne doit jamais se trouver (principe 8 de la spec D2). */
const leakedChannels = (onAnnounce: ReturnType<typeof vi.fn>, consoleSpies: ReturnType<typeof vi.spyOn>[]) => {
  const channels: Record<string, string> = {
    sessionStorage: JSON.stringify({ ...sessionStorage }),
    localStorage: JSON.stringify({ ...localStorage }),
    queryCache: JSON.stringify(client.getQueryCache().getAll().map((q) => [q.queryKey, q.state.data])),
    mutationCache: JSON.stringify(client.getMutationCache().getAll().map((m) => [m.state.variables, m.state.data])),
    toasts: JSON.stringify([vi.mocked(toast.success).mock.calls, vi.mocked(toast.error).mock.calls, vi.mocked(toast.info).mock.calls]),
    announce: JSON.stringify(onAnnounce.mock.calls),
    liveRegions: Array.from(document.querySelectorAll("[aria-live], [role=status], [role=alert]"))
      .map((node) => node.textContent)
      .join("|"),
    attributes: Array.from(document.querySelectorAll("*"))
      .flatMap((node) => Array.from(node.attributes).filter((a) => a.name !== "value").map((a) => a.value))
      .join("|"),
    console: JSON.stringify(consoleSpies.map((spy) => spy.mock.calls)),
    url: window.location.href,
  };
  return Object.entries(channels)
    .filter(([, value]) => value.includes(SENTINEL))
    .map(([name]) => name);
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

// ---------------------------------------------------------------------------------------------------------------------
describe("Section « À traiter » et carte de demande (E6, spec D2 §4.4, §4.5)", () => {
  it("can_confirm : nom abrégé, indice lu chiffre par chiffre, dates, créateur, consigne d'appel, boutons nommés", async () => {
    const { get } = renderSection();
    expect(await screen.findByRole("heading", { level: 2, name: "À traiter" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Demandes d'accès à confirmer" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: "Marie K. a accepté l'invitation" })).toBeInTheDocument();
    expect(screen.getByText("Téléphone se terminant par ••47")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("Téléphone se terminant par 4 7")).toHaveClass("sr-only");
    expect(screen.getByText(/^Acceptée le/)).toBeInTheDocument();
    expect(screen.getByText(/^À confirmer avant le/)).toBeInTheDocument();
    expect(screen.getByText("Créée par vous")).toBeInTheDocument();
    expect(screen.getByText("Toute l'organisation")).toBeInTheDocument();
    expect(screen.getByText(/appelez la personne au numéro que vous connaissez/)).toBeInTheDocument();
    expect(screen.getByText(/Ne demandez pas le code par message/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmer l'accès de Marie K." })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Rejeter la demande de Marie K." })).toBeEnabled();
    expect(screen.queryByText(/ne peut plus donner ce rôle/)).not.toBeInTheDocument();
    // Requête de la section : statut AWAITING_CONFIRMATION, sur la route des invitations de l'organisation
    expect(get).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/`, { params: { status: "AWAITING_CONFIRMATION" } });
  });

  it("can_confirm faux : carte anonyme, aucun bouton, texte « Seuls la personne… »", async () => {
    renderSection([awaiting(INV1, { can_confirm: false, accepted_by_display_name: null, accepted_by_phone_hint: null, is_mine: false })]);
    expect(await screen.findByRole("heading", { level: 4, name: "Une personne a accepté une invitation comme Administrateur" })).toBeInTheDocument();
    expect(screen.getByText("Créée par Paul M.")).toBeInTheDocument();
    expect(screen.getByText(/Seuls la personne qui a créé l'invitation et les administrateurs principaux/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/Téléphone se terminant/)).not.toBeInTheDocument();
  });

  it("inviter_has_authority faux : avertissement (icône + texte), sur les deux variantes", async () => {
    renderSection([
      awaiting(INV1, { inviter_has_authority: false }),
      awaiting(INV2, { inviter_has_authority: false, can_confirm: false, accepted_by_display_name: null, accepted_by_phone_hint: null }),
    ]);
    await screen.findByText("Marie K. a accepté l'invitation");
    expect(screen.getAllByText(/La personne qui a créé cette invitation ne peut plus donner ce rôle/)).toHaveLength(2);
  });

  it("tri : can_confirm d'abord, puis l'échéance la plus proche ; lignes non AWAITING ignorées", async () => {
    renderSection([
      awaiting(INV2, { can_confirm: false, accepted_by_display_name: null, accepted_by_phone_hint: null }),
      awaiting("44444444-4444-4444-8444-444444444443", { accepted_by_display_name: "Jean T.", confirmation_expires_at: "2026-11-29T00:00:00Z" }),
      awaiting(INV1, { confirmation_expires_at: "2026-11-27T00:00:00Z" }),
      awaiting("44444444-4444-4444-8444-444444444444", { status: "EXPIRED", accepted_by_display_name: "Échu E." }),
    ]);
    await screen.findByText("Marie K. a accepté l'invitation");
    const titles = screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
    expect(titles).toEqual(["Marie K. a accepté l'invitation", "Jean T. a accepté l'invitation", "Une personne a accepté une invitation comme Administrateur"]);
  });

  it("vide : section absente ; sans org.manage_members : aucune requête", async () => {
    const { get } = renderSection([]);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "À traiter" })).not.toBeInTheDocument();
    vi.restoreAllMocks();
    const second = renderSection([awaiting(INV1)], { ...ORG_FULL, capabilities: ["org.view_internal"] });
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(second.get).not.toHaveBeenCalled();
  });

  it("erreur : ligne compacte « Impossible de vérifier… » + Réessayer", async () => {
    const { get } = renderSection(new Error("x"));
    expect(await screen.findByText("Impossible de vérifier les demandes en attente.")).toBeInTheDocument();
    const calls = get.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(calls));
  });

  it("hors ligne : carte conservée, boutons désactivés avec la raison", async () => {
    online.value = false;
    renderSection();
    const confirm = await screen.findByRole("button", { name: "Confirmer l'accès de Marie K." });
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("button", { name: "Rejeter la demande de Marie K." })).toBeDisabled();
    expect(confirm).toHaveAccessibleDescription("Reconnectez-vous pour effectuer cette action.");
  });
});

// ---------------------------------------------------------------------------------------------------------------------
describe("E6g : confirmer l'accès avec le code de rattachement (spec D2 §8.3)", () => {
  it("structure : consigne d'appel, récapitulatif, champ code (focus initial, numérique, sans saisie automatique), bouton désactivé", async () => {
    renderSection();
    const dialog = await openConfirm();
    expect(within(dialog).getByText("Appelez d'abord la personne")).toBeInTheDocument();
    expect(within(dialog).getByText(/pas à un numéro reçu avec la demande/)).toBeInTheDocument();
    expect(within(dialog).getByText("Vérifiez que ces chiffres correspondent au numéro que vous appelez.")).toBeInTheDocument();
    expect(within(dialog).getByText(/devient Administrateur de « Boutique Lumière » immédiatement/)).toBeInTheDocument();
    const code = codeField(dialog);
    await waitFor(() => expect(code).toHaveFocus());
    expect(code).toHaveAttribute("autocomplete", "off");
    expect(code).toHaveAttribute("inputmode", "numeric");
    // Pas de maxLength (il tronquerait un collage avant normalisation) ; collage normalisé
    expect(code).not.toHaveAttribute("maxlength");
    fireEvent.paste(code, { clipboardData: { getData: () => "Code : 482-913 merci" } });
    expect(code).toHaveValue(SENTINEL);
    fireEvent.change(code, { target: { value: "" } });
    // Gestionnaire de mots de passe : identifiant du compte caché, en lecture seule, en tête du formulaire, une seule fois
    const usernames = dialog.querySelectorAll('input[name="username"]');
    expect(usernames).toHaveLength(1);
    const username = usernames[0] as HTMLInputElement;
    expect(username).toHaveAttribute("autocomplete", "username");
    expect(username).toHaveAttribute("readonly");
    expect(username.hidden).toBe(true);
    expect(username.value).toBe("+243810000047");
    expect(username.compareDocumentPosition(code) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(code).toHaveAccessibleDescription(/par exemple 482 913/);
    expect(within(dialog).getByRole("checkbox", { name: /J'ai obtenu ce code en appelant Marie K./ })).toBeInTheDocument();
    expect(submitButton(dialog)).toBeDisabled();
    // Pas de bouton Copier, pas de six cases
    expect(within(dialog).queryByRole("button", { name: /Copier/ })).not.toBeInTheDocument();
    expect(within(dialog).getAllByRole("textbox")).toHaveLength(1);
  });

  it("saisie : chiffres seulement, espaces RETIRÉS ; corps {confirm, password, code} ; succès : toast, annonce, sans code", async () => {
    const { onAnnounce, onFocusFallback } = renderSection();
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { membership_id: "m", display_name: "Marie K.", role: "ADMIN" } });
    const dialog = await openConfirm();
    fireEvent.change(codeField(dialog), { target: { value: "48a2 9" } });
    expect(codeField(dialog)).toHaveValue("4829");
    expect(submitButton(dialog)).toBeDisabled();
    fillAll(dialog, "482 913");
    expect(codeField(dialog)).toHaveValue(SENTINEL);
    fireEvent.click(submitButton(dialog));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/${INV1}/confirm/`, { confirm: true, password: PASSWORD, code: SENTINEL });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Marie K. a rejoint l'équipe comme Administrateur.");
    expect(onAnnounce).toHaveBeenCalledWith("Marie K. a rejoint l'équipe comme Administrateur.");
    await waitFor(() => expect(onFocusFallback).toHaveBeenCalled());
  });

  it("403 reauthentication_failed : erreur sous le mot de passe, mot de passe vidé, CODE CONSERVÉ, focus mot de passe", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(403, "reauthentication_failed"));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    expect(await within(dialog).findByText("Mot de passe incorrect. Aucun essai de code n'a été compté.")).toBeInTheDocument();
    expect(passwordField(dialog)).toHaveValue("");
    expect(codeField(dialog)).toHaveValue(SENTINEL);
    await waitFor(() => expect(passwordField(dialog)).toHaveFocus());
    expect(passwordField(dialog)).toHaveAttribute("aria-invalid", "true");
  });

  it("400 confirmation_code_invalid : erreur sous le code, CODE VIDÉ, mot de passe conservé, focus code, aucun nombre d'essais", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(400, "confirmation_code_invalid"));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    const error = await within(dialog).findByText(/Ce code est incorrect. Vérifiez-le avec Marie K. au téléphone/);
    expect(error.textContent).not.toMatch(/\d/);
    expect(codeField(dialog)).toHaveValue("");
    expect(codeField(dialog)).toHaveAttribute("aria-invalid", "true");
    expect(passwordField(dialog)).toHaveValue(PASSWORD);
    await waitFor(() => expect(codeField(dialog)).toHaveFocus());
  });

  it("400 confirmation_code_required : texte « Saisissez les 6 chiffres », focus code", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(400, "confirmation_code_required"));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    expect(await within(dialog).findByText("Saisissez les 6 chiffres du code.")).toBeInTheDocument();
    await waitFor(() => expect(codeField(dialog)).toHaveFocus());
  });

  it("409 confirmation_code_exhausted : fermeture, toast 10 s, annonce, rechargement", async () => {
    const { get, onAnnounce } = renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(409, "confirmation_code_exhausted"));
    const dialog = await openConfirm();
    const before = get.mock.calls.length;
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const text = "Trop de codes incorrects : la demande a été rejetée automatiquement. Si cette personne doit rejoindre l'équipe, créez une nouvelle invitation.";
    expect(toast.error).toHaveBeenCalledWith(text, { duration: 10_000 });
    expect(onAnnounce).toHaveBeenCalledWith(text);
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(before));
  });

  it.each([
    ["404 invitation_not_found", apiError(404, "invitation_not_found"), "info", "Cette demande n'est plus en attente : elle a été traitée, retirée, rejetée ou a expiré."],
    ["409 invitation_not_awaiting_confirmation", apiError(409, "invitation_not_awaiting_confirmation"), "info", "Cette demande n'est plus en attente : elle a été traitée, retirée, rejetée ou a expiré."],
    ["403 DENY_PERMISSION", apiError(403, "DENY_PERMISSION"), "error", "Vous ne pouvez plus confirmer cette demande. Un administrateur principal peut le faire."],
    ["409 already_member", apiError(409, "already_member"), "info", "Cette personne fait déjà partie de l'équipe."],
  ])("%s : fermeture et toast", async (_label, error, level, text) => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast[level as "info" | "error"]).toHaveBeenCalledWith(text);
  });

  it("403 DENY_RELATION : fermeture et information (comme classifyTeamError), code et mot de passe effacés", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(403, "DENY_RELATION"));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.error).toHaveBeenCalledWith("Vous n'avez pas accès à cet élément.");
    const again = await openConfirm();
    expect(codeField(again)).toHaveValue("");
    expect(passwordField(again)).toHaveValue("");
  });

  it.each(["DENY_SECURITY", "DENY_OBJECT_STATE"])("403 %s : alerte dans le dialogue, code ET mot de passe effacés", async (code) => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(403, code));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    await waitFor(() => expect(within(dialog).getByRole("alert")).toBeInTheDocument());
    expect(codeField(dialog)).toHaveValue("");
    expect(passwordField(dialog)).toHaveValue("");
    expect(within(dialog).getByRole("checkbox")).not.toBeChecked();
  });

  it("400 user_unavailable : alerte, code et mot de passe vidés, dialogue ouvert", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(400, "user_unavailable"));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    expect(await within(dialog).findByText(/Cette personne ne peut pas rejoindre l'organisation pour le moment/)).toBeInTheDocument();
    expect(codeField(dialog)).toHaveValue("");
    expect(passwordField(dialog)).toHaveValue("");
  });

  it("réseau coupé : texte « L'accès a peut-être été confirmé », code conservé, AUCUNE relance automatique", async () => {
    renderSection();
    const post = vi.spyOn(apiClient, "post").mockRejectedValue(NETWORK);
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    expect(await within(dialog).findByText(/L'accès a peut-être été confirmé : vérifiez la liste avant de réessayer/)).toBeInTheDocument();
    expect(codeField(dialog)).toHaveValue(SENTINEL);
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("429 : message et bouton bloqué", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(429, undefined, { "retry-after": "60" }));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    expect(await within(dialog).findByText("Trop de tentatives. Réessayez dans quelques minutes.")).toBeInTheDocument();
    expect(submitButton(dialog)).toBeDisabled();
  });

  it("inviter_has_authority faux : avertissement en tête du dialogue", async () => {
    renderSection([awaiting(INV1, { inviter_has_authority: false })]);
    const dialog = await openConfirm();
    expect(within(dialog).getByText(/ne peut plus donner ce rôle \(elle a changé de rôle ou quitté l'équipe\)/)).toBeInTheDocument();
  });

  it("SENTINELLE : après échecs et fermeture, « 482913 » n'est dans aucun stockage, cache, région vivante, toast, attribut, URL ni console", async () => {
    const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level));
    const { onAnnounce } = renderSection();
    const post = vi
      .spyOn(apiClient, "post")
      .mockRejectedValueOnce(apiError(403, "reauthentication_failed"))
      .mockRejectedValueOnce(NETWORK)
      .mockRejectedValueOnce(apiError(400, "confirmation_code_invalid"));
    const dialog = await openConfirm();
    fillAll(dialog);
    fireEvent.click(submitButton(dialog));
    await within(dialog).findByText(/Mot de passe incorrect/);
    // Pendant l'échec, rien n'a fui (le code n'existe que dans la valeur du champ)
    expect(leakedChannels(onAnnounce, consoleSpies)).toEqual([]);
    fireEvent.change(passwordField(dialog), { target: { value: PASSWORD } });
    fireEvent.click(submitButton(dialog));
    await within(dialog).findByText(/Connexion perdue/);
    expect(leakedChannels(onAnnounce, consoleSpies)).toEqual([]);
    fireEvent.click(submitButton(dialog));
    await within(dialog).findByText(/Ce code est incorrect/);
    expect(post).toHaveBeenCalledTimes(3);
    expect(leakedChannels(onAnnounce, consoleSpies)).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(leakedChannels(onAnnounce, consoleSpies)).toEqual([]);
    expect(document.body.innerHTML).not.toContain(SENTINEL);
    // Rouvert : champs vides
    const again = await openConfirm();
    expect(codeField(again)).toHaveValue("");
    expect(passwordField(again)).toHaveValue("");
  });
});

// ---------------------------------------------------------------------------------------------------------------------
describe("E6h : rejeter une demande (spec D2 §8.4)", () => {
  const openReject = async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Rejeter la demande de Marie K." }));
    return screen.findByRole("alertdialog", { name: "Rejeter la demande de Marie K. ?" });
  };

  it("structure : texte, consigne, focus sur « Garder la demande », ni mot de passe ni code", async () => {
    renderSection();
    const dialog = await openReject();
    expect(within(dialog).getByText(/Elle sera prévenue, sans voir votre nom/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Rejetez si la personne que vous avez appelée n'a pas de code/)).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Garder la demande" })).toHaveFocus());
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/ne peut plus donner ce rôle/)).not.toBeInTheDocument();
  });

  it("succès : POST reject/ sans corps, toast et annonce", async () => {
    const { onAnnounce } = renderSection();
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: undefined });
    const dialog = await openReject();
    fireEvent.click(within(dialog).getByRole("button", { name: "Rejeter" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/invitations/${INV1}/reject/`));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Demande rejetée.");
    expect(onAnnounce).toHaveBeenCalledWith("Demande rejetée.");
  });

  it("409 invitation_not_awaiting_confirmation : toast « n'est plus en attente » ; DENY_PERMISSION : toast dédié", async () => {
    renderSection();
    const post = vi.spyOn(apiClient, "post").mockRejectedValueOnce(apiError(409, "invitation_not_awaiting_confirmation")).mockRejectedValueOnce(apiError(403, "DENY_PERMISSION"));
    let dialog = await openReject();
    fireEvent.click(within(dialog).getByRole("button", { name: "Rejeter" }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Cette demande n'est plus en attente : elle a été traitée, retirée, rejetée ou a expiré."));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    dialog = await openReject();
    fireEvent.click(within(dialog).getByRole("button", { name: "Rejeter" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Vous ne pouvez plus confirmer cette demande. Un administrateur principal peut le faire."));
    expect(post).toHaveBeenCalledTimes(2);
  });

  it("inviter_has_authority faux : phrase ajoutée", async () => {
    renderSection([awaiting(INV1, { inviter_has_authority: false })]);
    const dialog = await openReject();
    expect(within(dialog).getByText("La personne qui a créé cette invitation ne peut plus donner ce rôle.")).toBeInTheDocument();
  });

  it("403 DENY_RELATION : fermeture et information", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(403, "DENY_RELATION"));
    const dialog = await openReject();
    fireEvent.click(within(dialog).getByRole("button", { name: "Rejeter" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(toast.error).toHaveBeenCalledWith("Vous n'avez pas accès à cet élément.");
  });

  it("hors ligne : « Rejeter » désactivé, relié à la mention hors ligne", async () => {
    const { RejectAdminInvitationDialog } = await import("./RejectAdminInvitationDialog");
    client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <RejectAdminInvitationDialog orgId={ORG} invitation={awaiting(INV1)} online={false} onClose={vi.fn()} onDone={vi.fn()} onAnnounce={vi.fn()} />
      </QueryClientProvider>,
    );
    const reject = within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Rejeter" });
    expect(reject).toBeDisabled();
    expect(reject).toHaveAccessibleDescription("Reconnectez-vous pour effectuer cette action.");
  });

  it("réseau : « Connexion perdue », dialogue ouvert", async () => {
    renderSection();
    vi.spyOn(apiClient, "post").mockRejectedValue(NETWORK);
    const dialog = await openReject();
    fireEvent.click(within(dialog).getByRole("button", { name: "Rejeter" }));
    expect(await within(dialog).findByText("Connexion perdue. Réessayez quand vous êtes reconnecté.")).toBeInTheDocument();
  });
});
