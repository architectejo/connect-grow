import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import apiClient from "@/api/client";
import { contextsKeys } from "./use-contexts";
import {
  organizationKeys,
  useArchiveOrganization,
  useCreateOrganization,
  useDeleteOrganizationDocument,
  useLeaveOrganization,
  useOrganization,
  useOrganizationDocuments,
  useOrganizationLimits,
  useUpdateOrganization,
  useUploadOrganizationDocument,
} from "./use-organizations";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));

const ORG = "11111111-1111-4111-8111-111111111111";
const DOC = "22222222-2222-4222-8222-222222222222";
const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };

describe("hooks d'organisation", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lit les limites, le détail interne et les pièces aux chemins du contrat", async () => {
    const get = vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => ({
      data: url.endsWith("kyc/documents/") ? { count: 0, next: null, previous: null, results: [] } : { id: ORG },
    }));
    const wrapper = wrapperFor(newClient());
    renderHook(() => useOrganizationLimits(), { wrapper });
    renderHook(() => useOrganization(ORG), { wrapper });
    const docs = renderHook(() => useOrganizationDocuments(ORG), { wrapper });
    await waitFor(() => expect(docs.result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith("accounts/organizations/limits/");
    expect(get).toHaveBeenCalledWith(`accounts/organizations/${ORG}/internal/`);
    expect(get).toHaveBeenCalledWith(`accounts/organizations/${ORG}/kyc/documents/`);
  });

  it("ne lit pas les pièces quand la lecture est désactivée (rôle sans org.verification_submit)", () => {
    const get = vi.spyOn(apiClient, "get");
    const docs = renderHook(() => useOrganizationDocuments(ORG, { enabled: false }), { wrapper: wrapperFor(newClient()) });
    expect(get).not.toHaveBeenCalled();
    expect(docs.result.current.fetchStatus).toBe("idle");
  });

  it("ne lit rien sans identifiant", () => {
    const get = vi.spyOn(apiClient, "get");
    renderHook(() => useOrganization(undefined), { wrapper: wrapperFor(newClient()) });
    expect(get).not.toHaveBeenCalled();
  });

  it("création : POST, puis cache du détail et rechargement de la liste des profils", async () => {
    const created = { id: ORG, name: "Aide Kin" };
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: created });
    const client = newClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useCreateOrganization(), { wrapper: wrapperFor(client) });
    await act(() => result.current.mutateAsync({ name: "Aide Kin", org_type: "ONG" }));
    expect(post).toHaveBeenCalledWith("accounts/organizations/", { name: "Aide Kin", org_type: "ONG" });
    expect(client.getQueryData(organizationKeys.internal(ORG))).toEqual(created);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: contextsKeys.all });
  });

  it("modification : PATCH sur l'organisation", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: { id: ORG } });
    const { result } = renderHook(() => useUpdateOrganization(ORG), { wrapper: wrapperFor(newClient()) });
    await act(() => result.current.mutateAsync({ description: "Texte" }));
    expect(patch).toHaveBeenCalledWith(`accounts/organizations/${ORG}/`, { description: "Texte" });
  });

  it("archivage : l'action de sortie du profil actif passe AVANT le rechargement des profils", async () => {
    const order: string[] = [];
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: ORG, status: "ARCHIVED" } });
    const client = newClient();
    vi.spyOn(client, "invalidateQueries").mockImplementation(async () => {
      order.push("invalidate");
    });
    const { result } = renderHook(() => useArchiveOrganization(ORG, () => order.push("before")), { wrapper: wrapperFor(client) });
    await act(() => result.current.mutateAsync());
    expect(order).toEqual(["before", "invalidate"]);
  });

  it("départ : POST leave/, détail retiré du cache, profils rechargés après la sortie du profil actif", async () => {
    const order: string[] = [];
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ status: 204, data: "" });
    const client = newClient();
    client.setQueryData(organizationKeys.internal(ORG), { id: ORG });
    vi.spyOn(client, "invalidateQueries").mockImplementation(async () => {
      order.push("invalidate");
    });
    const { result } = renderHook(() => useLeaveOrganization(ORG, () => order.push("before")), { wrapper: wrapperFor(client) });
    await act(() => result.current.mutateAsync());
    expect(post).toHaveBeenCalledWith(`accounts/organizations/${ORG}/leave/`);
    expect(client.getQueryData(organizationKeys.internal(ORG))).toBeUndefined();
    expect(order).toEqual(["before", "invalidate"]);
  });

  it("dépôt d'une pièce : multipart document_type + file, jamais d'autre champ", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: DOC } });
    const { result } = renderHook(() => useUploadOrganizationDocument(ORG), { wrapper: wrapperFor(newClient()) });
    const file = new File(["%PDF"], "rccm.pdf", { type: "application/pdf" });
    await act(() => result.current.mutateAsync({ type: "RCCM", file }));
    const [url, body] = post.mock.calls[0] as [string, FormData];
    expect(url).toBe(`accounts/organizations/${ORG}/kyc/documents/`);
    expect(body).toBeInstanceOf(FormData);
    expect([...body.keys()].sort()).toEqual(["document_type", "file"]);
    expect(body.get("document_type")).toBe("RCCM");
  });

  it("suppression d'une pièce : DELETE sur la pièce de l'organisation", async () => {
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ status: 204 });
    const { result } = renderHook(() => useDeleteOrganizationDocument(ORG), { wrapper: wrapperFor(newClient()) });
    await act(() => result.current.mutateAsync(DOC));
    expect(del).toHaveBeenCalledWith(`accounts/organizations/${ORG}/kyc/documents/${DOC}/`);
  });

  it("une pièce déposée relance la lecture de l'état de vérification et des pièces", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: DOC } });
    const client = newClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useUploadOrganizationDocument(ORG), { wrapper: wrapperFor(client) });
    await act(() => result.current.mutateAsync({ type: "RCCM", file: new File(["x"], "a.pdf") }));
    const keys = invalidate.mock.calls.map(([filter]) => JSON.stringify((filter as { queryKey: unknown }).queryKey));
    expect(keys).toEqual(
      expect.arrayContaining([
        JSON.stringify(organizationKeys.verification(ORG)),
        JSON.stringify(organizationKeys.documents(ORG)),
        JSON.stringify(organizationKeys.internal(ORG)),
      ]),
    );
  });
});
