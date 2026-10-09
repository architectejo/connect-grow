import { useRef } from "react";
import { Navigate } from "react-router-dom";
import { BadgeCheck, CheckCircle2, Clock, FileText, Loader2, Lock, Trash2, Upload, XCircle, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { KycDocument, KycDocumentType, KycStatus } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AccountShell } from "@/components/layout/AccountShell";
import { ErrorState, PageHeader } from "@/components/common";
import { useAuth } from "@/contexts/AuthContext";
import { useDeleteKyc, useKycDocuments, useUploadKyc } from "@/hooks/use-account";
import { formatRelativeDate } from "@/lib/format";
import { formatFileSize } from "@/lib/image";
import { cn } from "@/lib/utils";

// CDC 3.1 : RCCM, identification nationale, pièce d'identité du gérant
const DOCUMENTS: { type: KycDocumentType; title: string; description: string }[] = [
  { type: "RCCM", title: "Registre du commerce (RCCM)", description: "Extrait ou certificat d'immatriculation de l'entreprise." },
  { type: "ID_NATIONALE", title: "Identification nationale", description: "Attestation d'identification nationale de l'entreprise." },
  { type: "PIECE_GERANT", title: "Pièce d'identité du gérant", description: "Carte d'électeur, passeport ou permis de conduire en cours de validité." },
];

const ACCEPTED = ["application/pdf", "image/jpeg", "image/png"];
const MAX_SIZE = 10 * 1024 * 1024;

const STATUS: Record<KycStatus, { label: string; icon: LucideIcon; tone: string }> = {
  EN_ATTENTE: { label: "En cours d'examen", icon: Clock, tone: "bg-warning/15 text-foreground" },
  VALIDE: { label: "Validé", icon: CheckCircle2, tone: "bg-success/10 text-success" },
  REFUSE: { label: "Refusé", icon: XCircle, tone: "bg-destructive/10 text-destructive" },
};

function DocumentRow({ spec, latest }: { spec: (typeof DOCUMENTS)[number]; latest?: KycDocument }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { t } = useTranslation();
  const upload = useUploadKyc();
  const remove = useDeleteKyc();
  const status = latest ? STATUS[latest.status] : null;
  const canUpload = !latest || latest.status === "REFUSE";

  const onFile = (file?: File) => {
    if (!file) return;
    if (!ACCEPTED.includes(file.type)) {
      toast.error("Formats acceptés : PDF, JPG ou PNG.");
      return;
    }
    if (file.size > MAX_SIZE) {
      toast.error(`Fichier trop lourd (${formatFileSize(file.size)}). 10 Mo maximum.`);
      return;
    }
    upload.mutate({ type: spec.type, file });
  };

  return (
    <li className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <FileText className="h-5 w-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{spec.title}</p>
        <p className="text-sm text-muted-foreground">{spec.description}</p>
        {status && latest && (
          <p className={cn("mt-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", status.tone)}>
            <status.icon className="h-3.5 w-3.5" aria-hidden /> {status.label}
            <span className="font-normal opacity-80">· envoyé {formatRelativeDate(latest.created_at)}</span>
          </p>
        )}
        {latest?.status === "REFUSE" && latest.rejection_reason && (
          <p className="mt-2 rounded-lg bg-destructive/5 p-3 text-sm text-foreground">
            <span className="font-semibold">Motif du refus : </span>
            {latest.rejection_reason}
          </p>
        )}
      </div>
      {latest && latest.status !== "VALIDE" && (
        // Une pièce validée ne peut pas être supprimée (le serveur la refuse)
        <Button
          variant="ghost"
          className="shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => remove.mutate(latest.id)}
          disabled={remove.isPending}
          aria-label={t("kyc.deleteLabel", { title: spec.title })}
        >
          {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Trash2 aria-hidden />}
          {t("kyc.delete")}
        </Button>
      )}
      {canUpload && (
        <>
          <Button variant={latest ? "default" : "outline"} className="shrink-0" onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Upload aria-hidden />}
            {latest ? "Envoyer à nouveau" : "Envoyer"}
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED.join(",")}
            className="sr-only"
            tabIndex={-1}
            onChange={(e) => {
              onFile(e.target.files?.[0]);
              e.target.value = "";
            }}
            aria-label={`Envoyer : ${spec.title}`}
          />
        </>
      )}
    </li>
  );
}

/** Vérification d'un Profil Business par pièces justificatives (CDC 3.1, 3.11). */
const Verification = () => {
  const { user } = useAuth();
  const isBusiness = user?.user_type === "ENTREPRISE";
  const { data: documents = [], isLoading, isError, refetch } = useKycDocuments(isBusiness);

  if (user && !isBusiness) return <Navigate to="/settings" replace />;

  const verified = !!user?.business_profile?.is_verified;
  // Document le plus récent pour chaque type
  const latestByType = new Map<KycDocumentType, KycDocument>();
  [...documents]
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .forEach((doc) => latestByType.set(doc.document_type, doc));
  const sent = DOCUMENTS.filter((d) => latestByType.has(d.type)).length;

  return (
    <AccountShell>
      <PageHeader
        title="Vérification de la boutique"
        description="Le badge Vérifié rassure les acheteurs : il indique que votre entreprise existe et que son gérant est identifié."
      />

      <div
        className={cn(
          "mb-6 flex items-start gap-4 rounded-2xl border p-5",
          verified ? "border-success/30 bg-success/5" : "bg-card shadow-soft",
        )}
      >
        <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl", verified ? "bg-success/15 text-success" : "bg-muted text-muted-foreground")}>
          <BadgeCheck className="h-6 w-6" aria-hidden />
        </span>
        <div className="flex-1">
          <p className="font-bold">{verified ? "Votre boutique est vérifiée" : `${sent}/${DOCUMENTS.length} documents envoyés`}</p>
          <p className="text-sm text-muted-foreground">
            {verified
              ? "Le badge Vérifié apparaît sur vos annonces et votre vitrine."
              : "Nos modérateurs examinent chaque document. Vous serez notifié de leur décision."}
          </p>
          {!verified && (
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${(sent / DOCUMENTS.length) * 100}%` }} />
            </div>
          )}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-72 rounded-2xl" />
      ) : isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : (
        <ul className="divide-y overflow-hidden rounded-2xl border bg-card shadow-soft">
          {DOCUMENTS.map((spec) => (
            <DocumentRow key={spec.type} spec={spec} latest={latestByType.get(spec.type)} />
          ))}
        </ul>
      )}

      <p className="mt-4 flex items-start gap-2 text-xs text-muted-foreground">
        <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        Vos documents sont stockés dans un espace privé, accessible uniquement aux administrateurs habilités. Ils ne sont jamais publiés.
      </p>
    </AccountShell>
  );
};

export default Verification;
