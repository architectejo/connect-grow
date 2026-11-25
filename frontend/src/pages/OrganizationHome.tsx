import { useId } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";
import type { OrganizationInternal } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PageHeader, RoleBadge, SellerTypeBadge, UserAvatar, VerifiedClaims } from "@/components/common";
import { LegacyOrgNotice } from "@/components/profiles/LegacyOrgNotice";
import { ArchiveOrganizationCard, LeaveOrganizationCard } from "@/components/organizations/OrganizationActions";
import { OrganizationPage } from "@/components/organizations/OrganizationPage";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { capabilityLabelKeys } from "@/lib/organization-form";
import { sellerPath } from "@/lib/post";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="rounded-2xl border bg-card p-5 shadow-soft">
      <h2 id={id} className="font-display text-lg font-bold">
        {title}
      </h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Overview({ org }: { org: OrganizationInternal }) {
  const { t } = useTranslation();
  const location = useLocation();
  const { active, setActive, contexts } = useActiveContext();
  const justCreated = (location.state as { justCreated?: boolean } | null)?.justCreated === true;
  const isActive = active.type === "ORGANIZATION" && active.id === org.id;
  const inList = contexts.find((c) => c.type === "ORGANIZATION" && c.id === org.id);
  const canSubmit = org.capabilities.includes("org.verification_submit");
  const capabilityKeys = capabilityLabelKeys(org.capabilities);

  return (
    <>
      <PageHeader
        eyebrow={t(`orgType.${org.org_type}`)}
        title={org.name}
        description={org.description || undefined}
        actions={
          isActive ? (
            <span className="inline-flex min-h-10 items-center rounded-full bg-primary/10 px-4 text-sm font-semibold">{t("profiles.isActive")}</span>
          ) : inList ? (
            <Button type="button" onClick={() => setActive(inList)}>
              {t("org.home.activate")}
            </Button>
          ) : null
        }
      />

      {justCreated && (
        <Alert className="mb-4 border-success/40">
          <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
          <AlertTitle>{t("org.home.createdTitle")}</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>{t("org.home.createdBody")}</p>
            {canSubmit && (
              <Button asChild size="sm">
                <Link to={`/organizations/${org.id}/verification`}>{t("org.home.createdAction")}</Link>
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      <LegacyOrgNotice only={org.id} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t("org.home.roleTitle")}>
          <RoleBadge role={org.my_role} />
          <p className="mt-2 text-sm text-muted-foreground">{t(`role.${org.my_role}_desc`)}</p>
          <h3 className="mt-4 text-sm font-semibold">{t("org.home.canTitle")}</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {capabilityKeys.map((key) => (
              <li key={key}>{t(key)}</li>
            ))}
          </ul>
        </Card>

        <Card title={t("org.home.verificationTitle")}>
          {org.verification.verified_claims.length > 0 ? (
            <VerifiedClaims claims={org.verification.verified_claims} summary={org.verification.summary} />
          ) : (
            <p className="text-sm text-muted-foreground">{t("org.home.noClaims")}</p>
          )}
          <Button asChild variant="link" className="mt-2 h-auto p-0">
            <Link to={`/organizations/${org.id}/verification`}>{t("org.home.seeDetail")}</Link>
          </Button>
        </Card>

        <Card title={t("org.home.publicTitle")}>
          <div className="flex items-center gap-3">
            <UserAvatar src={org.logo} name={org.name} size="md" shape="square" />
            <div className="min-w-0 space-y-1">
              <p className="truncate font-semibold" title={org.name}>
                {org.name}
              </p>
              <SellerTypeBadge contextType="ORGANIZATION" orgType={org.org_type} />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-3">
            <Button asChild variant="link" className="h-auto p-0">
              <Link to={sellerPath("ORGANIZATION", org.id)}>{t("org.home.seePublic")}</Link>
            </Button>
            {org.capabilities.includes("org.edit_profile") && (
              <Button asChild variant="link" className="h-auto p-0">
                <Link to={`/organizations/${org.id}/edit`}>{t("org.home.editProfile")}</Link>
              </Button>
            )}
          </div>
        </Card>

        <LeaveOrganizationCard org={org} />
        <ArchiveOrganizationCard org={org} />
      </div>
    </>
  );
}

const OrganizationHome = () => <OrganizationPage section="overview">{(org) => <Overview org={org} />}</OrganizationPage>;

export default OrganizationHome;
