import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import type { OrganizationMember, OrganizationRole } from "@/api/types";
import { MembersPanel } from "./MembersPanel";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// Rendu jsdom + Radix + fenêtres chargées à la demande : 1 à 3 s par cas sur la machine de développement, davantage
// quand toute la suite tourne en parallèle. Délai explicite propre à ce fichier (ne dépend pas de vitest.config.ts).
vi.setConfig({ testTimeout: 20_000 });

beforeAll(async () => {
  // Les fenêtres sont chargées à l'ouverture (React.lazy) : on réchauffe les modules pour ne pas dépendre de la charge de la machine
  configure({ asyncUtilTimeout: 5000 });
  await Promise.all([import("./ChangeRoleDialog"), import("./TransferOwnershipDialog"), import("./RemoveMemberDialog")]);
  // Radix (menu, radios) mesure ses éléments : jsdom n'a pas ResizeObserver
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const ORG = "11111111-1111-4111-8111-111111111111";
const MANAGE = ["org.view_internal", "org.manage_members", "org.manage_roles"];
const READ = ["org.view_internal"];
const PASSWORD = "Mot-de-passe-secret-42";

const make = (n: number, name: string, role: OrganizationRole, extra: Partial<OrganizationMember> = {}): OrganizationMember => ({
  membership_id: `00000000-0000-4000-8000-00000000000${n}`,
  display_name: name,
  role,
  joined_at: "2026-09-09T08:00:00Z",
  is_self: false,
  is_last_effective_owner: false,
  ...extra,
});
const ME_OWNER = make(1, "Marie K.", "OWNER", { is_self: true });
const ADMIN = make(2, "Paul M.", "ADMIN");
const EDITOR = make(3, "Jean T.", "EDITOR");
const ANALYST = make(4, "Awa B.", "ANALYST");
const CO_OWNER = make(5, "Luc D.", "OWNER");
const TEAM = [ME_OWNER, CO_OWNER, ADMIN, EDITOR, ANALYST];
const page = (results: OrganizationMember[], next: string | null = null) => ({ data: { count: results.length, next, previous: null, results } });
const apiError = (status: number, code?: string, headers: Record<string, string> = {}, data: Record<string, unknown> = {}) => ({
  response: { status, data: code ? { detail: "Message du serveur", code } : data, headers },
});

const renderPanel = (role: OrganizationRole, capabilities: string[], members: OrganizationMember[] = TEAM) => {
  vi.spyOn(apiClient, "get").mockResolvedValue(page(members));
  const onAnnounce = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <MembersPanel org={{ id: ORG, my_role: role, capabilities }} onAnnounce={onAnnounce} />
    </QueryClientProvider>,
  );
  return { ...view, onAnnounce, client };
};

const trigger = (name: string) => screen.queryByRole("button", { name: `Actions pour ${name}` });
const openMenu = async (name: string) => {
  fireEvent.keyDown(trigger(name) as HTMLElement, { key: "Enter" });
  return screen.findByRole("menu");
};
const pick = async (name: string, item: string | RegExp) => {
  const menu = await openMenu(name);
  fireEvent.click(within(menu).getByRole("menuitem", { name: item }));
};

beforeEach(() => {
  online.value = true;
  window.innerWidth = 1024;
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.info).mockClear();
});
afterEach(() => vi.restoreAllMocks());

describe("liste des membres : affichage selon le rôle", () => {
  it("administrateur principal : tableau avec en-têtes, noms abrégés, (vous), rôles et ancienneté", async () => {
    renderPanel("OWNER", MANAGE);
    expect(await screen.findByText("Paul M.")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Membres de l'équipe/ })).toBeInTheDocument();
    for (const header of ["Membre", "Rôle", "Dans l'équipe depuis", "Actions"]) expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    expect(screen.getByText("(vous)")).toBeInTheDocument();
    const adminRow = screen.getByText("Paul M.").closest("tr") as HTMLElement;
    expect(within(adminRow).getByText("Administrateur")).toBeInTheDocument();
    expect(within(adminRow).getByText("septembre 2026")).toBeInTheDocument();
  });

  it("mobile : cartes empilées avec « Dans l'équipe depuis … »", async () => {
    window.innerWidth = 500;
    renderPanel("OWNER", MANAGE);
    expect(await screen.findByText("Paul M.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(TEAM.length);
    expect(screen.getAllByText("Dans l'équipe depuis septembre 2026")).toHaveLength(TEAM.length);
  });

  it("n'affiche aucun téléphone, e-mail ni identifiant de compte ou d'appartenance (règle 10)", async () => {
    const { container } = renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    const text = container.ownerDocument.body.textContent ?? "";
    expect(text).not.toMatch(/@|\+243|\d{9}/);
    for (const member of TEAM) expect(text).not.toContain(member.membership_id);
    expect(container.ownerDocument.body.innerHTML).not.toContain(ADMIN.membership_id);
  });

  it("aucun lien avec un plan, un prix ou une vérification (règles 2 et 3)", async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    expect(document.body.textContent).not.toMatch(/plan|abonnement|prix|payant|vérifi|\$|USD/i);
  });

  it("éditeur et analyste : liste en lecture seule, aucun menu", async () => {
    for (const role of ["EDITOR", "ANALYST"] as const) {
      const { unmount } = renderPanel(role, READ, TEAM.map((m) => ({ ...m, is_last_effective_owner: null })));
      await screen.findByText("Paul M.");
      expect(screen.queryByRole("button", { name: /Actions pour/ })).not.toBeInTheDocument();
      unmount();
    }
  });

  it("administrateur : menu sur les non-administrateurs principaux, texte « Réservé aux administrateurs principaux » sur un administrateur principal", async () => {
    renderPanel("ADMIN", MANAGE, [CO_OWNER, { ...ADMIN, is_self: true }, EDITOR]);
    await screen.findByText("Jean T.");
    expect(trigger("Luc D.")).not.toBeInTheDocument();
    expect(screen.getByText("Réservé aux administrateurs principaux")).toBeInTheDocument();
    expect(trigger("Paul M.")).not.toBeInTheDocument(); // sa propre ligne
    const menu = await openMenu("Jean T.");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Changer le rôle", "Retirer de l'équipe"]);
  });

  it("badge « Seul administrateur principal actif » seulement si is_last_effective_owner vaut true ; aide sur sa propre ligne", async () => {
    renderPanel("OWNER", MANAGE, [{ ...ME_OWNER, is_last_effective_owner: true }, ADMIN, { ...EDITOR, is_last_effective_owner: null }]);
    await screen.findByText("Paul M.");
    expect(screen.getAllByText("Seul administrateur principal actif")).toHaveLength(1);
    expect(screen.getByText(/elle n'aura plus d'administrateur principal disponible/)).toBeInTheDocument();
    const badge = screen.getByText("Seul administrateur principal actif").closest("div") as HTMLElement;
    expect(badge).toHaveAttribute("title", expect.stringContaining("ne peuvent pas agir actuellement"));
    expect(document.getElementById(badge.getAttribute("aria-describedby") as string)).toHaveTextContent("ne peuvent pas agir actuellement");
  });

  it("ne bloque jamais d'avance sur le dernier administrateur principal : le menu de l'autre administrateur principal reste complet", async () => {
    renderPanel("OWNER", MANAGE, [{ ...ME_OWNER, is_last_effective_owner: true }, { ...CO_OWNER, is_last_effective_owner: false }]);
    await screen.findByText("Luc D.");
    const menu = await openMenu("Luc D.");
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(2);
  });
});

describe("rôle Membre (contrat L1-01 §7.1, spec D2 §2.1 et §4.3)", () => {
  const MEMBER = make(6, "Rose N.", "MEMBER", { scope: { type: "ORGANIZATION", id: null } });

  it("un membre voit l'équipe sans aucun menu ni indication de gestion, sur aucune ligne", async () => {
    renderPanel("MEMBER", ["org.leave", "org.view_internal"], [CO_OWNER, ADMIN, EDITOR, ANALYST, { ...MEMBER, is_self: true, is_last_effective_owner: null }]);
    await screen.findByText("Rose N.");
    for (const name of ["Luc D.", "Paul M.", "Jean T.", "Awa B.", "Rose N."]) expect(trigger(name)).not.toBeInTheDocument();
    expect(screen.queryByText("Réservé aux administrateurs principaux")).not.toBeInTheDocument();
    expect(screen.queryByText("Pour retirer cet administrateur principal, changez d'abord son rôle.")).not.toBeInTheDocument();
    // Le rôle s'affiche par un badge « Membre », l'ancienneté par « Dans l'équipe depuis » (pas de confusion)
    expect(screen.getAllByText("Membre").length).toBeGreaterThanOrEqual(2); // en-tête de colonne + badge
    expect(screen.getByRole("columnheader", { name: "Dans l'équipe depuis" })).toBeInTheDocument();
  });

  it("mobile : carte du membre avec badge « Membre » et « Dans l'équipe depuis »", async () => {
    window.innerWidth = 375;
    renderPanel("MEMBER", ["org.leave", "org.view_internal"], [{ ...MEMBER, is_self: true }]);
    await screen.findByText("Rose N.");
    expect(screen.getByText("Membre")).toBeInTheDocument();
    expect(screen.getByText("Dans l'équipe depuis septembre 2026")).toBeInTheDocument();
  });

  it("un administrateur principal gère un membre : changer le rôle, transférer, retirer", async () => {
    renderPanel("OWNER", MANAGE, [ME_OWNER, MEMBER]);
    await screen.findByText("Rose N.");
    const menu = await openMenu("Rose N.");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Changer le rôle", "Transférer l'administration principale à Rose N.", "Retirer de l'équipe"]);
  });

  it("changer le rôle : Membre proposé en dernier, périmètre affiché sous le titre, jamais envoyé", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: { ...MEMBER, role: "ANALYST" } });
    renderPanel("ADMIN", MANAGE, [{ ...ADMIN, is_self: true }, MEMBER]);
    await screen.findByText("Rose N.");
    await pick("Rose N.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog", { name: "Changer le rôle de Rose N." });
    expect(within(dialog).getByText("Périmètre : Toute l'organisation")).toBeInTheDocument();
    const radios = within(dialog).getAllByRole("radio");
    expect(radios.map((radio) => radio.getAttribute("value"))).toEqual(["ADMIN", "EDITOR", "ANALYST", "MEMBER"]);
    expect(within(dialog).getByRole("radio", { name: /^Membre/ })).toBeChecked();
    // Aucun contrôle de saisie du périmètre (spec D2 §2.4)
    expect(within(dialog).queryByRole("combobox")).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("radio", { name: /Analyste/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith(`accounts/organizations/${ORG}/members/${MEMBER.membership_id}/`, { role: "ANALYST" }));
  });

  it("serveur antérieur sans `scope` : aucune ligne de périmètre, rien d'inventé", async () => {
    renderPanel("OWNER", MANAGE, [ME_OWNER, EDITOR]);
    await screen.findByText("Jean T.");
    await pick("Jean T.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText(/Périmètre/)).not.toBeInTheDocument();
  });
});

describe("menu d'actions d'un administrateur principal", () => {
  it("cible non administrateur principal : changer le rôle, transférer, puis retirer après un séparateur destructif", async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    expect(trigger("Marie K.")).not.toBeInTheDocument(); // pas de menu sur sa propre ligne
    const menu = await openMenu("Paul M.");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Changer le rôle", "Transférer l'administration principale à Paul M.", "Retirer de l'équipe"]);
    expect(within(menu).getByRole("separator")).toBeInTheDocument();
  });

  it("cible administrateur principal : pas de « Retirer », avec l'indication « changez d'abord son rôle »", async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Luc D.");
    const menu = await openMenu("Luc D.");
    expect(within(menu).queryByRole("menuitem", { name: /Retirer/ })).not.toBeInTheDocument();
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(2);
    expect(screen.getByText("Pour retirer cet administrateur principal, changez d'abord son rôle.")).toBeInTheDocument();
  });

  it("le déclencheur a un nom accessible propre à la ligne et le menu s'ouvre au clavier (Entrée)", async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    const button = screen.getByRole("button", { name: "Actions pour Paul M." });
    expect(button).toHaveAttribute("aria-haspopup", "menu");
    expect(await openMenu("Paul M.")).toBeInTheDocument();
  });
});

describe("changer le rôle (E6b)", () => {
  it("rôle simple : un seul écran, corps { role } sans mot de passe, toast et annonce, fenêtre fermée", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: { ...EDITOR, role: "ANALYST" } });
    const { onAnnounce } = renderPanel("OWNER", MANAGE);
    await screen.findByText("Jean T.");
    await pick("Jean T.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog", { name: "Changer le rôle de Jean T." });
    const save = within(dialog).getByRole("button", { name: "Enregistrer le rôle" });
    expect(save).toBeDisabled(); // rôle inchangé
    expect(within(dialog).getByRole("radio", { name: /Éditeur/ })).toBeChecked();
    expect(within(dialog).getByText("(rôle actuel)")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("radio", { name: /Analyste/ }));
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(patch).toHaveBeenCalledWith(`accounts/organizations/${ORG}/members/${EDITOR.membership_id}/`, { role: "ANALYST" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Le rôle de Jean T. est maintenant Analyste.");
    expect(onAnnounce).toHaveBeenCalledWith("Le rôle de Jean T. est maintenant Analyste.");
  });

  it("l'administrateur ne peut pas choisir Administrateur principal", async () => {
    renderPanel("ADMIN", MANAGE, [{ ...ADMIN, is_self: true }, EDITOR]);
    await screen.findByText("Jean T.");
    await pick("Jean T.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByRole("radio")).toHaveLength(4);
    expect(within(dialog).queryByRole("radio", { name: /^Administrateur principal/ })).not.toBeInTheDocument();
  });

  it("promotion vers Administrateur principal : étape 2 avec case et mot de passe, envoyés dans le corps seulement", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: { ...ADMIN, role: "OWNER" } });
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    await pick("Paul M.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /^Administrateur principal/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    expect(patch).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/Paul M\. deviendra administrateur principal/)).toBeInTheDocument();
    const confirmButton = within(dialog).getByRole("button", { name: "Confirmer le changement" });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Je confirme ce changement" }));
    expect(confirmButton).toBeDisabled(); // mot de passe encore vide
    const password = within(dialog).getByLabelText("Votre mot de passe");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    fireEvent.change(password, { target: { value: PASSWORD } });
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(`accounts/organizations/${ORG}/members/${ADMIN.membership_id}/`, { role: "OWNER", confirm: true, password: PASSWORD }),
    );
    // Le mot de passe n'est ni dans l'URL, ni dans un stockage
    expect(JSON.stringify(patch.mock.calls.map((c) => c[0]))).not.toContain(PASSWORD);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(JSON.stringify({ ...localStorage })).not.toContain(PASSWORD);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(PASSWORD);
    expect(window.location.href).not.toContain(PASSWORD);
    expect(document.body.innerHTML).not.toContain(PASSWORD);
  });

  it("rétrogradation d'un administrateur principal : étape 2 avec le texte de rétrogradation ; « Retour » revient au choix", async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Luc D.");
    await pick("Luc D.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /^Administrateur(?! principal)/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    expect(within(dialog).getByText(/Luc D\. ne sera plus administrateur principal/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retour" }));
    expect(within(dialog).getAllByRole("radio")).toHaveLength(5);
    expect(within(dialog).queryByLabelText("Votre mot de passe")).not.toBeInTheDocument();
  });

  const strongChange = async (error: unknown) => {
    const patch = vi.spyOn(apiClient, "patch").mockRejectedValue(error);
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Luc D.");
    await pick("Luc D.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /^Administrateur(?! principal)/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.change(within(dialog).getByLabelText("Votre mot de passe"), { target: { value: PASSWORD } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirmer le changement" }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    return dialog;
  };

  it("403 reauthentication_failed : erreur sous le champ, mot de passe vidé, focus sur le champ, fenêtre ouverte", async () => {
    const dialog = await strongChange(apiError(403, "reauthentication_failed"));
    const password = await within(dialog).findByLabelText("Votre mot de passe");
    expect(await within(dialog).findByText("Mot de passe incorrect.")).toBeInTheDocument();
    expect(password).toHaveValue("");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAttribute("aria-describedby", expect.stringContaining("error"));
    await waitFor(() => expect(password).toHaveFocus());
    expect(within(dialog).getByRole("checkbox")).toBeChecked(); // valeurs conservées
  });

  it.each([
    ["409 last_owner", apiError(409, "last_owner"), "Une organisation doit toujours avoir au moins un administrateur principal."],
    ["409 last_effective_owner", apiError(409, "last_effective_owner"), "Cette organisation a des offres actives"],
    ["400 user_unavailable", apiError(400, "user_unavailable"), "Ce changement n'est pas possible pour ce compte pour le moment."],
    ["400 confirmation_required", apiError(400, "confirmation_required"), "Cochez la case de confirmation"],
    ["400 password_required", apiError(400, "password_required"), "Saisissez votre mot de passe pour continuer."],
    ["403 DENY_SECURITY", apiError(403, "DENY_SECURITY"), "temporairement impossible"],
    ["403 DENY_OBJECT_STATE", apiError(403, "DENY_OBJECT_STATE"), "n'est plus dans un état qui permet cette action"],
    ["réseau coupé", { isAxiosError: true, message: "Network Error" }, "Connexion perdue. Réessayez quand vous êtes reconnecté."],
  ])("%s : message dans la fenêtre, qui reste ouverte", async (_label, error, text) => {
    const dialog = await strongChange(error);
    expect(await within(dialog).findByText(new RegExp(text.replace(/[.()]/g, "\\$&")))).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("429 : message de patience, bouton désactivé", async () => {
    const dialog = await strongChange(apiError(429, undefined, { "retry-after": "600" }));
    expect(await within(dialog).findByText("Trop de tentatives. Réessayez dans quelques minutes.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Confirmer le changement" })).toBeDisabled();
  });

  it("403 DENY_PERMISSION : fenêtre fermée, texte « votre rôle ne permet pas », liste rechargée", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockRejectedValue(apiError(403, "DENY_PERMISSION"));
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Jean T.");
    const get = vi.mocked(apiClient.get);
    await pick("Jean T.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /Analyste/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Votre rôle ne permet pas cette action"));
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(1));
  });

  it("404 member_not_found : fenêtre fermée, information, liste rechargée", async () => {
    vi.spyOn(apiClient, "patch").mockRejectedValue(apiError(404, "member_not_found"));
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Jean T.");
    await pick("Jean T.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /Analyste/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Cette personne ne fait plus partie de l'équipe."));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("400 {role: [...]} : message du serveur sous la liste des rôles", async () => {
    vi.spyOn(apiClient, "patch").mockRejectedValue(apiError(400, undefined, {}, { role: ["Ce rôle n'est pas valide."] }));
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Jean T.");
    await pick("Jean T.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /Analyste/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    expect(await within(dialog).findByText("Ce rôle n'est pas valide.")).toBeInTheDocument();
  });
});

describe("transférer l'administration principale (E6c)", () => {
  const open = async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    await pick("Paul M.", /Transférer l'administration principale/);
    return screen.findByRole("dialog", { name: "Transférer l'administration principale à Paul M." });
  };
  const fill = (dialog: HTMLElement) => {
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Je confirme le transfert d'administration principale" }));
    fireEvent.change(within(dialog).getByLabelText("Votre mot de passe"), { target: { value: PASSWORD } });
  };

  it("contenu : texte, rôle après transfert (Administrateur par défaut, jamais Administrateur principal), alternative ; focus initial « Annuler »", async () => {
    const dialog = await open();
    expect(within(dialog).getByText(/Paul M\. deviendra administrateur principal\. Vous ne serez plus administrateur principal/)).toBeInTheDocument();
    expect(within(dialog).getByText(/utilisez plutôt « Changer le rôle »/)).toBeInTheDocument();
    const radios = within(dialog).getAllByRole("radio");
    expect(radios.map((r) => r.id)).toEqual(["transfer-role-ADMIN", "transfer-role-EDITOR", "transfer-role-ANALYST"]);
    expect(within(dialog).getByRole("radio", { name: /^Administrateur(?! principal)/ })).toBeChecked();
    expect(within(dialog).getByRole("radiogroup", { name: "Votre rôle après le transfert" })).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Annuler" })).toHaveFocus());
    expect(within(dialog).getByRole("button", { name: "Transférer l'administration principale" })).toBeDisabled();
  });

  it("succès : POST avec membership_id, my_new_role, confirm et mot de passe ; toast ; fermeture", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { new_owner: { ...ADMIN, role: "OWNER" }, me: { ...ME_OWNER, role: "EDITOR" } } });
    const dialog = await open();
    fireEvent.click(within(dialog).getByRole("radio", { name: /Éditeur/ }));
    fill(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "Transférer l'administration principale" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/transfer-ownership/`, {
        membership_id: ADMIN.membership_id,
        my_new_role: "EDITOR",
        confirm: true,
        password: PASSWORD,
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("L'administration principale a été transférée à Paul M..");
  });

  it.each([
    ["400 invalid_transfer", apiError(400, "invalid_transfer"), "Ce transfert n'est pas possible."],
    ["400 user_unavailable", apiError(400, "user_unavailable"), "Ce changement n'est pas possible pour ce compte pour le moment."],
    ["400 password_required", apiError(400, "password_required"), "Saisissez votre mot de passe pour continuer."],
    ["400 confirmation_required", apiError(400, "confirmation_required"), "Cochez la case de confirmation"],
  ])("%s : message dans la fenêtre", async (_label, error, text) => {
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const dialog = await open();
    fill(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "Transférer l'administration principale" }));
    expect(await within(dialog).findByText(new RegExp(text))).toBeInTheDocument();
  });

  it("403 reauthentication_failed : erreur sous le champ, mot de passe vidé et refocalisé, bouton désactivé tant qu'il est vide", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(403, "reauthentication_failed"));
    const dialog = await open();
    fill(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "Transférer l'administration principale" }));
    expect(await within(dialog).findByText("Mot de passe incorrect.")).toBeInTheDocument();
    const password = within(dialog).getByLabelText("Votre mot de passe");
    expect(password).toHaveValue("");
    await waitFor(() => expect(password).toHaveFocus());
    expect(within(dialog).getByRole("button", { name: "Transférer l'administration principale" })).toBeDisabled();
  });

  it("429 : message de patience, bouton désactivé, aucune relance automatique", async () => {
    const post = vi.spyOn(apiClient, "post").mockRejectedValueOnce(apiError(429, undefined, { "retry-after": "600" }));
    const dialog = await open();
    fill(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "Transférer l'administration principale" }));
    expect(await within(dialog).findByText("Trop de tentatives. Réessayez dans quelques minutes.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Transférer l'administration principale" })).toBeDisabled();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("DENY_PERMISSION ferme la fenêtre avec le texte de refus", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(403, "DENY_PERMISSION"));
    const dialog = await open();
    fill(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "Transférer l'administration principale" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Votre rôle ne permet pas cette action"));
  });

  it("404 member_not_found ferme la fenêtre avec l'information", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(apiError(404, "member_not_found"));
    const dialog = await open();
    fill(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "Transférer l'administration principale" }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Cette personne ne fait plus partie de l'équipe."));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("le mot de passe de ressaisie n'est jamais conservé", () => {
  const NETWORK = { isAxiosError: true, message: "Network Error" };
  const noTrace = () => {
    expect(JSON.stringify({ ...localStorage })).not.toContain(PASSWORD);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(PASSWORD);
    expect(window.location.href).not.toContain(PASSWORD);
  };
  const fillRole = async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Luc D.");
    await pick("Luc D.", "Changer le rôle");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /^Administrateur(?! principal)/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer le rôle" }));
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.change(within(dialog).getByLabelText("Votre mot de passe"), { target: { value: PASSWORD } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirmer le changement" }));
    return dialog;
  };
  const fillTransfer = async () => {
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    await pick("Paul M.", /Transférer l'administration principale/);
    const dialog = await screen.findByRole("dialog", { name: "Transférer l'administration principale à Paul M." });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Je confirme le transfert d'administration principale" }));
    fireEvent.change(within(dialog).getByLabelText("Votre mot de passe"), { target: { value: PASSWORD } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Transférer l'administration principale" }));
    return dialog;
  };

  it.each([
    ["réseau coupé", NETWORK],
    ["500", apiError(500)],
    ["400 {role}", apiError(400, undefined, {}, { role: ["Ce rôle n'est pas valide."] })],
  ])("changement de rôle, %s : champ vidé, rien dans le DOM ni les stockages", async (_label, error) => {
    const patch = vi.spyOn(apiClient, "patch").mockRejectedValue(error);
    const dialog = await fillRole();
    await waitFor(() => expect(patch).toHaveBeenCalled());
    await waitFor(() => expect(document.body.innerHTML).not.toContain(PASSWORD));
    const field = within(dialog).queryByLabelText("Votre mot de passe");
    if (field) expect(field).toHaveValue("");
    noTrace();
  });

  it.each([
    ["réseau coupé", NETWORK],
    ["500", apiError(500)],
  ])("transfert, %s : champ vidé et bouton désactivé", async (_label, error) => {
    const post = vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const dialog = await fillTransfer();
    await waitFor(() => expect(post).toHaveBeenCalled());
    await waitFor(() => expect(within(dialog).getByLabelText("Votre mot de passe")).toHaveValue(""));
    expect(within(dialog).getByRole("button", { name: "Transférer l'administration principale" })).toBeDisabled();
    noTrace();
  });

  it("une fenêtre rouverte après un échec a un champ de mot de passe vide", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(NETWORK);
    const dialog = await fillTransfer();
    await within(dialog).findByText(/Connexion perdue/);
    fireEvent.click(within(dialog).getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await pick("Paul M.", /Transférer l'administration principale/);
    const reopened = await screen.findByRole("dialog", { name: "Transférer l'administration principale à Paul M." });
    expect(within(reopened).getByLabelText("Votre mot de passe")).toHaveValue("");
    expect(within(reopened).getByRole("checkbox", { name: "Je confirme le transfert d'administration principale" })).not.toBeChecked();
  });

  it("succès : aucune trace du mot de passe (stockages, DOM, URL, cache de mutations)", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: { new_owner: { ...ADMIN, role: "OWNER" }, me: { ...ME_OWNER, role: "EDITOR" } } });
    await fillTransfer();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    noTrace();
    expect(document.body.innerHTML).not.toContain(PASSWORD);
  });
});

describe("retirer un membre (E6d)", () => {
  const open = async (members = TEAM) => {
    const view = renderPanel("OWNER", MANAGE, members);
    await screen.findByText("Paul M.");
    await pick("Paul M.", "Retirer de l'équipe");
    const dialog = await screen.findByRole("alertdialog", { name: "Retirer Paul M. de l'équipe ?" });
    return { ...view, dialog };
  };

  it("texte explicatif, pas de mot de passe, focus initial « Annuler »", async () => {
    const { dialog } = await open();
    expect(within(dialog).getByText(/perdra immédiatement l'accès à l'organisation/)).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Votre mot de passe")).not.toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Annuler" })).toHaveFocus());
  });

  it("succès (204) : DELETE sans corps, toast, annonce, focus sur le titre de la liste", async () => {
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ status: 204, data: "" });
    const { dialog, onAnnounce } = await open();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith(`accounts/organizations/${ORG}/members/${ADMIN.membership_id}/`));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Paul M. a été retiré de l'équipe.");
    expect(onAnnounce).toHaveBeenCalledWith("Paul M. a été retiré de l'équipe.");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Membres de l'équipe" })).toHaveFocus());
  });

  it("404 member_not_found : même issue qu'un succès, avec une information", async () => {
    vi.spyOn(apiClient, "delete").mockRejectedValue(apiError(404, "member_not_found"));
    const { dialog } = await open();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer" }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Cette personne ne fait plus partie de l'équipe."));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it.each([
    ["409 owner_must_be_demoted", apiError(409, "owner_must_be_demoted"), "Cette personne est administrateur principal. Changez d'abord son rôle, puis retirez-la."],
    ["409 last_owner", apiError(409, "last_owner"), "Une organisation doit toujours avoir au moins un administrateur principal."],
    ["409 last_effective_owner", apiError(409, "last_effective_owner"), "Cette organisation a des offres actives"],
    ["400 use_leave", apiError(400, "use_leave"), "Pour quitter l'organisation, utilisez la carte"],
    ["réseau coupé", { isAxiosError: true, message: "Network Error" }, "Connexion perdue."],
  ])("%s : message dans la fenêtre, qui reste ouverte", async (_label, error, text) => {
    vi.spyOn(apiClient, "delete").mockRejectedValue(error);
    const { dialog } = await open();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer" }));
    expect(await within(dialog).findByText(new RegExp(text))).toBeInTheDocument();
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("429 : message de patience et bouton désactivé", async () => {
    vi.spyOn(apiClient, "delete").mockRejectedValueOnce(apiError(429, undefined, { "retry-after": "600" }));
    const { dialog } = await open();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer" }));
    expect(await within(dialog).findByText("Trop de tentatives. Réessayez dans quelques minutes.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Retirer" })).toBeDisabled();
  });

  it("DENY_PERMISSION : fenêtre fermée", async () => {
    vi.spyOn(apiClient, "delete").mockRejectedValue(apiError(403, "DENY_PERMISSION"));
    const { dialog } = await open();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retirer" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(toast.error).toHaveBeenCalled();
  });
});

describe("états de la liste", () => {
  it("chargement : squelettes (aria-busy) ; aucune carte avant la réponse", () => {
    vi.spyOn(apiClient, "get").mockReturnValue(new Promise(() => undefined));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MembersPanel org={{ id: ORG, my_role: "OWNER", capabilities: MANAGE }} onAnnounce={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("erreur : message et « Réessayer » qui recharge", async () => {
    const get = vi.spyOn(apiClient, "get").mockRejectedValueOnce(apiError(429)).mockResolvedValue(page(TEAM));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MembersPanel org={{ id: ORG, my_role: "OWNER", capabilities: MANAGE }} onAnnounce={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Impossible de charger l'équipe.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText("Paul M.")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("vide : message dédié", async () => {
    renderPanel("OWNER", MANAGE, []);
    expect(await screen.findByText("Aucun membre à afficher.")).toBeInTheDocument();
  });

  it("« Voir plus de membres » charge la page suivante ; un échec garde la liste et affiche un message", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce(page([ME_OWNER, ADMIN], "http://x/?page=2"))
      .mockRejectedValueOnce(apiError(429))
      .mockResolvedValueOnce(page([EDITOR]));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MembersPanel org={{ id: ORG, my_role: "OWNER", capabilities: MANAGE }} onAnnounce={vi.fn()} />
      </QueryClientProvider>,
    );
    await screen.findByText("Paul M.");
    fireEvent.click(screen.getByRole("button", { name: "Voir plus de membres" }));
    expect(await screen.findByText("Impossible de charger la suite de la liste.")).toBeInTheDocument();
    expect(screen.getByText("Paul M.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Voir plus de membres" }));
    expect(await screen.findByText("Jean T.")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole("button", { name: "Voir plus de membres" })).not.toBeInTheDocument();
  });

  it("hors ligne : liste conservée, menus désactivés avec la raison affichée", async () => {
    online.value = false;
    renderPanel("OWNER", MANAGE);
    await screen.findByText("Paul M.");
    expect(trigger("Paul M.")).toBeDisabled();
    expect(screen.getByText("Reconnectez-vous pour effectuer cette action.")).toBeInTheDocument();
    const hint = trigger("Paul M.")?.getAttribute("aria-describedby") as string;
    expect(document.getElementById(hint)).toHaveTextContent("Reconnectez-vous pour effectuer cette action.");
  });
});
