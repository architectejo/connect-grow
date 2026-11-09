import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Archive, PauseCircle } from "lucide-react";
import type { UnavailableOrganization } from "@/api/types";
import { PageHeader, RoleBadge, UserAvatar } from "@/components/common";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { LeaveOrganizationCard } from "@/components/organizations/OrganizationActions";
import { OrganizationStatusBadge } from "@/components/organizations/OrganizationStatusBadge";
import { cn } from "@/lib/utils";

const BLOCKED = ["offers", "profile", "verification", "messages", "team"] as const;

/**
 * Vue en lecture seule d'une organisation suspendue ou archivée (L0-09 UX-SUSP, 4.2). Un seul texte par statut,
 * sans motif ni auteur de décision (règle 10). Seule action : quitter l'organisation (`org.leave`, lue dans `capabilities`).
 * Rien n'est grisé : les actions impossibles sont absentes.
 */
export function OrganizationUnavailableView({ org }: { org: UnavailableOrganization }) {
  const { t } = useTranslation();
  const suspended = org.status === "SUSPENDED";
  const Icon = suspended ? PauseCircle : Archive;
  const recourseKey = `org.unavailable.recourse.${org.status}.${org.role === "OWNER" ? "OWNER" : "other"}`;
  const canLeave = (org.capabilities ?? []).includes("org.leave");

  useEffect(() => {
    const previous = document.title;
    document.title = t("org.unavailable.pageTitle", { name: org.name, status: t(`org.status.${org.status}`) });
    return () => {
      document.title = previous;
    };
  }, [org.name, org.status, t]);

  return (
    <div className="max-w-2xl">
      <PageHeader
        eyebrow={t(`orgType.${org.org_type}`)}
        title={
          <span className="flex items-center gap-3">
            <UserAvatar src={org.photo} name={org.name} size="md" shape="square" />
            <span className="min-w-0 truncate" title={org.name}>
              {org.name}
            </span>
          </span>
        }
        actions={<OrganizationStatusBadge status={org.status} />}
      />

      <div className="space-y-4">
        <Alert role="status" className={cn("bg-background", suspended ? "border-warning/60" : "border-border")}>
          <Icon className={cn("h-4 w-4", suspended ? "text-warning" : "text-muted-foreground")} aria-hidden />
          <AlertTitle>{t(`org.unavailable.title.${org.status}`)}</AlertTitle>
          <AlertDescription className="space-y-2 text-foreground">
            <p>{t(`org.unavailable.body.${org.status}`)}</p>
            {org.migrated_from_business && <p>{t("org.unavailable.migrated")}</p>}
            <p>{t(recourseKey)}</p>
          </AlertDescription>
        </Alert>

        <section aria-labelledby="unavailable-role" className="rounded-2xl border bg-card p-5 shadow-soft">
          <h2 id="unavailable-role" className="font-display text-lg font-bold">
            {t("org.home.roleTitle")}
          </h2>
          <div className="mt-2">
            <RoleBadge role={org.role} />
            <p className="mt-2 text-sm text-muted-foreground">{t(`role.${org.role}_desc`)}</p>
          </div>
        </section>

        <section aria-labelledby="unavailable-blocked" className="rounded-2xl border bg-card p-5 shadow-soft">
          <h2 id="unavailable-blocked" className="font-display text-lg font-bold">
            {t("org.unavailable.blockedTitle")}
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {BLOCKED.map((key) => (
              <li key={key}>{t(`org.unavailable.blocked.${key}`)}</li>
            ))}
          </ul>
        </section>

        {canLeave && <LeaveOrganizationCard org={org} bodyKey="org.unavailable.leaveBody" />}
      </div>
    </div>
  );
}
