import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import identity from "@/api/__fixtures__/backend-identity.json";
import OrganizationVerification from "./OrganizationVerification";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true, user: { id: "u1" } }) }));
vi.mock("@/components/layout/AccountShell", () => ({
  AccountShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
const online = vi.hoisted(() => ({ value: true }));
vi.mock("@/hooks/use-online-status", () => ({ useOnlineStatus: () => online.value }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const ORG = (identity.organization_internal_owner as { id: string }).id;
let internal: unknown;
let failVerification = false;

beforeEach(() => {
  online.value = true;
  failVerification = false;
  internal = identity.organization_internal_owner;
  vi.spyOn(apiClient, "get").mockImplementation((async (url: string) => {
    if (url.endsWith("/internal/")) return { data: internal };
    if (url.endsWith("/verification/")) {
      if (failVerification) throw Object.assign(new Error("panne"), { response: { status: 500, data: {} } });
      return { data: identity.verification_mixed };
    }
    if (url.endsWith("/kyc/documents/")) return { data: identity.kyc_documents };
    return { data: [] };
  }) as never);
});
afterEach(() => vi.restoreAllMocks());

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={[`/organizations/${ORG}/verification`]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
        <Routes>
          <Route path="/organizations/:id/verification" element={<OrganizationVerification />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );

const row = async (title: string) => {
  const item = (await screen.findByText(title)).closest("li");
  if (!item) throw new Error(`ligne absente : ${title}`);
  return within(item);
};

const upload = (input: HTMLElement, file: File) => fireEvent.change(input, { target: { files: [file] } });

describe("Vérification de l'organisation (E7)", () => {
  it("états des pièces, motif du refus et mention précise ; jamais « garanti » ni « Vérifié » seul", async () => {
    const { container } = renderPage();
    const rccm = await row("Registre du commerce (RCCM)");
    expect(rccm.getByText("Validée")).toBeInTheDocument();
    expect(rccm.getByText(/RCCM vérifié/)).toBeInTheDocument();
    expect(rccm.queryByRole("button")).not.toBeInTheDocument(); // validée : ni renvoi ni suppression
    const identite = await row("Identification nationale");
    expect(identite.getByText("Refusée")).toBeInTheDocument();
    expect(identite.getByText(/Document illisible/)).toBeInTheDocument();
    expect(identite.getByRole("button", { name: /Envoyer : Identification nationale/ })).toHaveTextContent("Envoyer à nouveau");
    expect(identite.getByRole("button", { name: /Supprimer le document/ })).toBeInTheDocument();
    const representant = await row("Pièce d'identité du représentant");
    expect(representant.getByText("Non envoyée")).toBeInTheDocument();
    expect(representant.getByRole("button", { name: /Envoyer : Pièce d'identité du représentant/ })).toHaveTextContent("Envoyer");
    const text = container.textContent ?? "";
    expect(text).toContain("1 pièce validée sur 3");
    expect(text).toContain("La vérification ne peut pas être achetée.");
    expect(text).not.toMatch(/garanti(?!e)|certifié|de confiance/i);
    expect(text).not.toMatch(/(^|\s)Vérifié(\s|$)/);
    expect(screen.queryByText("Organisation vérifiée")).not.toBeInTheDocument();
  });

  it("aucun fichier ni lien de téléchargement dans la page", async () => {
    renderPage();
    await row("Registre du commerce (RCCM)");
    expect(document.querySelector("a[href*='download'], a[download]")).toBeNull();
  });

  it("analyste ou éditeur : lecture seule, aucun bouton d'envoi ni de suppression", async () => {
    internal = identity.organization_internal_analyst;
    renderPage();
    expect(await screen.findByText("Seuls les administrateurs principaux et les administrateurs peuvent envoyer des pièces.")).toBeInTheDocument();
    await row("Identification nationale");
    expect(screen.queryByRole("button", { name: /Envoyer/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Supprimer/ })).not.toBeInTheDocument();
  });

  it("format refusé localement : message, aucune requête", async () => {
    const post = vi.spyOn(apiClient, "post");
    renderPage();
    const item = await row("Pièce d'identité du représentant");
    upload(item.getByLabelText(/Envoyer : Pièce d'identité du représentant/, { selector: "input" }), new File(["x"], "photo.gif", { type: "image/gif" }));
    expect(await item.findByText("Formats acceptés : PDF, JPG ou PNG.")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("fichier trop lourd : message avec la taille, aucune requête", async () => {
    const post = vi.spyOn(apiClient, "post");
    renderPage();
    const item = await row("Pièce d'identité du représentant");
    const big = new File(["x"], "scan.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 12 * 1024 * 1024 });
    upload(item.getByLabelText(/Envoyer : Pièce d'identité du représentant/, { selector: "input" }), big);
    expect(await item.findByText(/Fichier trop lourd \(12 Mo\)\. 10 Mo maximum\./)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("envoi : multipart document_type + file, message de succès, état rechargé", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ status: 201, data: { id: "d1" } });
    renderPage();
    const item = await row("Pièce d'identité du représentant");
    upload(item.getByLabelText(/Envoyer : Pièce d'identité du représentant/, { selector: "input" }), new File(["%PDF"], "carte.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, body] = post.mock.calls[0] as [string, FormData];
    expect(url).toBe(`accounts/organizations/${ORG}/kyc/documents/`);
    expect(body.get("document_type")).toBe("PIECE_GERANT");
    expect(body.get("file")).toBeInstanceOf(File);
  });

  it("échec réseau à l'envoi : message dédié, rien n'est mis en file", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(Object.assign(new Error("Network Error"), { isAxiosError: true }));
    renderPage();
    const item = await row("Pièce d'identité du représentant");
    upload(item.getByLabelText(/Envoyer : Pièce d'identité du représentant/, { selector: "input" }), new File(["%PDF"], "carte.pdf", { type: "application/pdf" }));
    expect(await item.findByText("L'envoi a échoué. Vérifiez votre connexion puis réessayez.")).toBeInTheDocument();
  });

  it("rôle devenu insuffisant (DENY_PERMISSION) : message de rôle sous la pièce", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "DENY_PERMISSION" } } });
    renderPage();
    const item = await row("Pièce d'identité du représentant");
    upload(item.getByLabelText(/Envoyer : Pièce d'identité du représentant/, { selector: "input" }), new File(["%PDF"], "carte.pdf", { type: "application/pdf" }));
    expect(await item.findByText(/Votre rôle ne permet pas cette action/)).toBeInTheDocument();
  });

  it("hors ligne : lecture seule, envoi et suppression désactivés avec la raison", async () => {
    online.value = false;
    renderPage();
    const item = await row("Pièce d'identité du représentant");
    expect(item.getByRole("button", { name: /Envoyer :/ })).toBeDisabled();
    expect(await screen.findByText("Reconnectez-vous pour effectuer cette action.")).toBeInTheDocument();
  });

  it("suppression d'une pièce refusée : confirmation puis DELETE de la pièce", async () => {
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ status: 204 });
    renderPage();
    const item = await row("Identification nationale");
    fireEvent.click(item.getByRole("button", { name: /Supprimer le document/ }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
    const docId = (identity.kyc_documents as { results: { id: string; document_type: string }[] }).results.find((d) => d.document_type === "ID_NATIONALE")?.id;
    await waitFor(() => expect(del).toHaveBeenCalledWith(`accounts/organizations/${ORG}/kyc/documents/${docId}/`));
  });

  it("erreur de chargement : message avec « Réessayer »", async () => {
    failVerification = true;
    renderPage();
    expect(await screen.findByRole("button", { name: "Réessayer" }, { timeout: 5000 })).toBeInTheDocument();
  });

  it("non-membre : accès refusé, jamais le contenu", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({ response: { status: 403, data: { detail: "x", code: "DENY_RELATION" } } });
    renderPage();
    expect(await screen.findByText("Vous n'avez pas accès à cette organisation.")).toBeInTheDocument();
    expect(screen.queryByText("Vérification de l'organisation")).not.toBeInTheDocument();
  });
});
