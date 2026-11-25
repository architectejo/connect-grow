import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Clock, FileText, Loader2, Trash2, Upload, XCircle, type LucideIcon } from "lucide-react";
import { toast } from "sonner";
import type { OrganizationKycDocument, RequirementStatus, Uuid, VerificationRequirement } from "@/api/types";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { claimLabel } from "@/components/common/VerifiedClaims";
import { useDeleteOrganizationDocument, useUploadOrganizationDocument } from "@/hooks/use-organizations";
import { describeApiError } from "@/lib/api-errors";
import { formatRelativeDate } from "@/lib/format";
import { formatFileSize } from "@/lib/image";
import { checkKycFile, KYC_ACCEPT_ATTR, uploadErrorMessage } from "@/lib/kyc-files";
import { httpStatus } from "@/lib/errors";
import { cn } from "@/lib/utils";

const STATE: Record<RequirementStatus, { icon: LucideIcon | null; tone: string }> = {
  MANQUANTE: { icon: null, tone: "bg-muted text-muted-foreground" },
  EN_ATTENTE: { icon: Clock, tone: "bg-warning/15 text-foreground" },
  VALIDE: { icon: CheckCircle2, tone: "bg-success/10 text-success" },
  REFUSE: { icon: XCircle, tone: "bg-destructive/10 text-destructive" },
};

interface DocumentRowProps {
  organizationId: Uuid;
  requirement: VerificationRequirement;
  /** Pièce la plus récente de ce type (sert à la date d'envoi et à la suppression). */
  latest?: OrganizationKycDocument;
  /** Capacité `org.verification_submit` : sinon aucun bouton d'envoi ni de suppression. */
  canSubmit: boolean;
  online: boolean;
}

/** Une pièce exigée : état, motif de refus, envoi et suppression. Aucun fichier ni URL n'est jamais affiché. */
export function DocumentRow({ organizationId, requirement, latest, canSubmit, online }: DocumentRowProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLParagraphElement>(null);
  const upload = useUploadOrganizationDocument(organizationId);
  const remove = useDeleteOrganizationDocument(organizationId);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string>();
  const status = requirement.status;
  const { icon: Icon, tone } = STATE[status] ?? STATE.MANQUANTE;
  const docType = requirement.document_type;
  const title = t(`kyc.docs.${docType}.title`, { defaultValue: requirement.document_type_label });
  const description = t(`kyc.docs.${docType}.description`, { defaultValue: "" });
  const canSend = canSubmit && (status === "MANQUANTE" || status === "REFUSE");
  const canDelete = canSubmit && (status === "EN_ATTENTE" || status === "REFUSE") && !!latest;

  const onFile = (file?: File) => {
    if (!file) return;
    setError(undefined);
    const problem = checkKycFile(file);
    if (problem) {
      setError(problem.kind === "format" ? t("verif.badFormat") : t("verif.tooHeavy", { size: formatFileSize(problem.size) }));
      return;
    }
    upload.mutate(
      { type: docType, file },
      {
        onSuccess: () => toast.success(t("verif.sent")),
        onError: (err) => setError(uploadErrorMessage(t, err)),
      },
    );
  };

  const doDelete = () => {
    if (!latest) return;
    setError(undefined);
    remove.mutate(latest.id, {
      onSuccess: () => {
        toast.success(t("verif.deleted"));
        titleRef.current?.focus();
      },
      onError: (err) => setError(httpStatus(err) === 409 ? t("verif.cannotDeleteValidated") : describeApiError(err, { inOrganization: true })),
    });
  };

  return (
    <li className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <FileText className="h-5 w-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p ref={titleRef} tabIndex={-1} className="font-semibold outline-none">
          {title}
        </p>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
        <p className={cn("mt-2 inline-flex flex-wrap items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", tone)}>
          {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
          {t(`verif.state.${status}`)}
          {status === "EN_ATTENTE" && latest && <span className="font-normal opacity-80">· {t("verif.sentOn", { date: formatRelativeDate(latest.uploaded_at) })}</span>}
          {status === "VALIDE" && <span className="font-normal">· {claimLabel(t, { code: requirement.claim_code, label: requirement.claim_label })}</span>}
        </p>
        {status === "REFUSE" &&
          (requirement.rejection_reason ? (
            <p className="mt-2 rounded-lg bg-destructive/5 p-3 text-sm text-foreground">
              <span className="font-semibold">{t("verif.rejectionReason")}</span>
              {requirement.rejection_reason}
            </p>
          ) : (
            // Motif masqué par le serveur pour les rôles sans `org.verification_submit` (L1-01-B6).
            <p className="mt-2 text-sm text-muted-foreground">{t("verif.rejectionReasonHidden")}</p>
          ))}
        {upload.isPending && (
          <p role="status" className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {t("verif.sending")}
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 text-sm font-medium text-destructive">
            {error}
          </p>
        )}
      </div>

      {canDelete && (
        <Button
          type="button"
          variant="ghost"
          className="shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => setConfirmDelete(true)}
          disabled={!online || remove.isPending || upload.isPending}
          aria-label={t("kyc.deleteLabel", { title })}
        >
          {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Trash2 aria-hidden />}
          {t("kyc.delete")}
        </Button>
      )}
      {canSend && (
        <>
          <Button
            type="button"
            variant={status === "REFUSE" ? "default" : "outline"}
            className="shrink-0"
            onClick={() => inputRef.current?.click()}
            disabled={!online || upload.isPending}
            aria-label={t("verif.sendAria", { title })}
          >
            {upload.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Upload aria-hidden />}
            {status === "REFUSE" ? t("verif.sendAgain") : t("verif.send")}
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={KYC_ACCEPT_ATTR}
            className="sr-only"
            tabIndex={-1}
            aria-label={t("verif.sendAria", { title })}
            onChange={(event) => {
              onFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </>
      )}

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("kyc.deleteConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("kyc.deleteConfirmDescription", { title })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={doDelete}>{t("kyc.delete")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}
