import { useTranslation } from "react-i18next";
import { Info, Lock } from "lucide-react";
import type { OrganizationInternal } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState, PageHeader, VerifiedClaims } from "@/components/common";
import { OrganizationPage } from "@/components/organizations/OrganizationPage";
import { DocumentRow } from "@/components/verification/DocumentRow";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useOrganizationDocuments, useOrganizationVerification } from "@/hooks/use-organizations";
import { latestByType } from "@/lib/kyc-files";

function VerificationContent({ org }: { org: OrganizationInternal }) {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  const verification = useOrganizationVerification(org.id);
  const canSubmit = org.capabilities.includes("org.verification_submit");
  // Détail des pièces réservé à `org.verification_submit` (L1-01-B6) : aucune requête pour les autres rôles.
  const documents = useOrganizationDocuments(org.id, { enabled: canSubmit });

  let body;
  if (verification.isLoading) {
    body = (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-24 rounded-2xl" />
        <Skeleton className="h-20 rounded-2xl" />
        <Skeleton className="h-20 rounded-2xl" />
        <Skeleton className="h-20 rounded-2xl" />
      </div>
    );
  } else if (verification.isError || !verification.data) {
    body = <ErrorState description={t("org.loadError")} onRetry={() => verification.refetch()} isRetrying={verification.isFetching} />;
  } else {
    const { requirements, verified_claims: claims, summary } = verification.data;
    // Après une rétrogradation, ne pas réutiliser des pièces restées en cache.
    const latest = latestByType(canSubmit ? (documents.data ?? []) : []);
    const validated = requirements.filter((item) => item.status === "VALIDE").length;
    body = (
      <>
        <section aria-labelledby="verif-claims" className="mb-4 rounded-2xl border bg-card p-5 shadow-soft">
          <h2 id="verif-claims" className="font-display text-lg font-bold">
            {t("verif.claimsTitle")}
          </h2>
          <div className="mt-2">
            {claims.length > 0 ? <VerifiedClaims claims={claims} summary={summary} /> : <p className="text-sm text-muted-foreground">{t("verif.noClaims")}</p>}
          </div>
          {requirements.length > 0 && (
            <p className="mt-3 text-sm text-muted-foreground">{t("verif.validatedCount", { count: validated, total: requirements.length })}</p>
          )}
        </section>

        <Alert className="mb-4">
          <Info className="h-4 w-4" aria-hidden />
          <AlertDescription>{t("verif.notPaid")}</AlertDescription>
        </Alert>

        {!canSubmit && (
          <Alert className="mb-4">
            <Lock className="h-4 w-4" aria-hidden />
            <AlertDescription>{t("verif.readOnly")}</AlertDescription>
          </Alert>
        )}

        {requirements.length === 0 ? (
          <EmptyState title={t("verif.noRequirements")} />
        ) : (
          <ul className="divide-y overflow-hidden rounded-2xl border bg-card shadow-soft">
            {requirements.map((requirement) => (
              <DocumentRow
                key={requirement.document_type}
                organizationId={org.id}
                requirement={requirement}
                latest={latest.get(requirement.document_type)}
                canSubmit={canSubmit}
                online={online}
              />
            ))}
          </ul>
        )}
        {!online && canSubmit && <p className="mt-3 text-sm text-muted-foreground">{t("common.offlineAction")}</p>}

        <p className="mt-4 flex items-start gap-2 text-xs text-muted-foreground">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {t("verif.privacy")}
        </p>
      </>
    );
  }

  return (
    <>
      <PageHeader title={t("verif.title")} description={t("verif.description")} />
      {body}
    </>
  );
}

const OrganizationVerification = () => <OrganizationPage section="verification">{(org) => <VerificationContent org={org} />}</OrganizationPage>;

export default OrganizationVerification;
