import type { TFunction } from "i18next";
import type { OrganizationKycDocument } from "@/api/types";
import { describeApiError, getApiErrorCode, isNetworkError } from "@/lib/api-errors";
import { httpStatus } from "@/lib/errors";
import { parseApiErrors } from "@/lib/validation";

/** Contrôles locaux d'une pièce de vérification avant envoi (le serveur contrôle à nouveau le contenu réel). */
export const KYC_ACCEPTED_TYPES = ["application/pdf", "image/jpeg", "image/png"];
export const KYC_ACCEPT_ATTR = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
export const KYC_MAX_SIZE = 10 * 1024 * 1024;

export type KycFileProblem = { kind: "format" } | { kind: "size"; size: number };

const EXTENSIONS = /\.(pdf|jpe?g|png)$/i;

/** null si le fichier peut être envoyé. Pas de compression : un justificatif doit rester lisible (D5). */
export function checkKycFile(file: Pick<File, "name" | "type" | "size">): KycFileProblem | null {
  const typeOk = file.type ? KYC_ACCEPTED_TYPES.includes(file.type) : EXTENSIONS.test(file.name);
  if (!typeOk) return { kind: "format" };
  if (file.size > KYC_MAX_SIZE) return { kind: "size", size: file.size };
  return null;
}

/** Message d'une erreur d'envoi de pièce. Après un échec réseau, le fichier doit être re-sélectionné (rien n'est mis en file). */
export function uploadErrorMessage(t: TFunction, error: unknown): string {
  if (isNetworkError(error)) return t("verif.sendFailed");
  if (getApiErrorCode(error)) return describeApiError(error, { inOrganization: true });
  const { fields, general } = parseApiErrors(error);
  if (httpStatus(error) === 400 && fields.document_type) return t("verif.notRequired");
  return fields.file ?? general ?? t("verif.sendFailed");
}

/** Pièce la plus récente de chaque type de document. */
export function latestByType(documents: OrganizationKycDocument[]): Map<string, OrganizationKycDocument> {
  const latest = new Map<string, OrganizationKycDocument>();
  [...documents]
    .sort((a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime())
    .forEach((doc) => {
      if (!latest.has(doc.document_type)) latest.set(doc.document_type, doc);
    });
  return latest;
}
