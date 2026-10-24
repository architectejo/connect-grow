import { describe, expect, it } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { OrganizationKycDocument } from "@/api/types";
import { checkKycFile, KYC_MAX_SIZE, latestByType, uploadErrorMessage } from "./kyc-files";

const file = (name: string, type: string, size = 1000) => ({ name, type, size });
const fail = (status: number, data: unknown) => ({ response: { status, data, headers: {} } });

describe("checkKycFile", () => {
  it("accepte PDF, JPG et PNG jusqu'à 10 Mo", () => {
    expect(checkKycFile(file("a.pdf", "application/pdf"))).toBeNull();
    expect(checkKycFile(file("a.jpg", "image/jpeg"))).toBeNull();
    expect(checkKycFile(file("a.png", "image/png", KYC_MAX_SIZE))).toBeNull();
  });
  it("refuse un autre format", () => {
    expect(checkKycFile(file("a.gif", "image/gif"))).toEqual({ kind: "format" });
    expect(checkKycFile(file("a.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))).toEqual({ kind: "format" });
  });
  it("refuse plus de 10 Mo en donnant la taille", () => {
    expect(checkKycFile(file("a.pdf", "application/pdf", KYC_MAX_SIZE + 1))).toEqual({ kind: "size", size: KYC_MAX_SIZE + 1 });
  });
  it("type MIME vide : l'extension décide", () => {
    expect(checkKycFile(file("scan.PDF", ""))).toBeNull();
    expect(checkKycFile(file("scan.exe", ""))).toEqual({ kind: "format" });
  });
});

describe("uploadErrorMessage", () => {
  const t = i18n.t.bind(i18n);
  it("réseau coupé : message d'échec, le fichier devra être re-sélectionné", () => {
    expect(uploadErrorMessage(t, Object.assign(new Error("Network Error"), { isAxiosError: true }))).toBe("L'envoi a échoué. Vérifiez votre connexion puis réessayez.");
  });
  it("type non exigé (400 sur document_type) : texte dédié", () => {
    expect(uploadErrorMessage(t, fail(400, { document_type: ["Cette pièce n'est pas exigée pour ce type d'organisation."] }))).toBe(
      "Cette pièce n'est pas demandée pour ce type d'organisation.",
    );
  });
  it("fichier refusé par le serveur : message du champ file", () => {
    expect(uploadErrorMessage(t, fail(400, { file: ["Format non accepté."] }))).toBe("Format non accepté.");
  });
  it("rôle insuffisant (DENY_PERMISSION) : message de rôle, sans nom de personne", () => {
    expect(uploadErrorMessage(t, fail(403, { detail: "x", code: "DENY_PERMISSION" }))).toMatch(/Votre rôle ne permet pas cette action/);
  });
  it("trop de tentatives (429) : délai en français", () => {
    expect(uploadErrorMessage(t, fail(429, { detail: "Requête ralentie. Réessayez dans 12 secondes.", code: "throttled" }))).toMatch(/12 secondes/);
  });
});

describe("latestByType", () => {
  const doc = (id: string, document_type: OrganizationKycDocument["document_type"], uploaded_at: string): OrganizationKycDocument => ({
    id,
    document_type,
    document_type_label: document_type,
    status: "EN_ATTENTE",
    uploaded_at,
  });
  it("garde la pièce la plus récente de chaque type", () => {
    const latest = latestByType([doc("old", "RCCM", "2026-10-01T10:00:00Z"), doc("new", "RCCM", "2026-10-05T10:00:00Z"), doc("id", "ID_NATIONALE", "2026-10-02T10:00:00Z")]);
    expect(latest.get("RCCM")?.id).toBe("new");
    expect(latest.get("ID_NATIONALE")?.id).toBe("id");
    expect(latest.size).toBe(2);
  });
});
