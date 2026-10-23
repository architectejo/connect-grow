import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import type { OrganizationRole } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PageHeader, RoleBadge } from "@/components/common";
import { LeaveOrganizationCard } from "@/components/organizations/OrganizationActions";
import { OrganizationPage } from "@/components/organizations/OrganizationPage";
import { cn } from "@/lib/utils";

const ROLES: OrganizationRole[] = ["OWNER", "ADMIN", "EDITOR", "ANALYST"];

/**
 * Équipe, version réduite de L0-09 (D11) : mon rôle, ce que chaque rôle peut faire, quitter l'organisation.
 * Aucun endpoint de liste ni de gestion des membres n'existe encore (L1-01) : rien d'autre n'est affiché,
 * et aucune donnée personnelle de membre n'est lue.
 */
const OrganizationTeam = () => {
  const { t } = useTranslation();
  return (
    <OrganizationPage section="team">
      {(org) => (
        <>
          <PageHeader title={t("team.title")} />
          <Alert className="mb-4">
            <Info className="h-4 w-4" aria-hidden />
            <AlertDescription>{t("team.notAvailable")}</AlertDescription>
          </Alert>

          <div className="grid gap-4 lg:grid-cols-2">
            <section aria-labelledby="team-your-role" className="rounded-2xl border bg-card p-5 shadow-soft">
              <h2 id="team-your-role" className="font-display text-lg font-bold">
                {t("team.yourRole")}
              </h2>
              <div className="mt-2">
                <RoleBadge role={org.my_role} />
                <p className="mt-2 text-sm text-muted-foreground">{t(`role.${org.my_role}_desc`)}</p>
              </div>
            </section>

            <LeaveOrganizationCard org={org} titleKey="team.leaveTitle" bodyKey="org.home.leaveBody" />
          </div>

          <section aria-labelledby="team-roles" className="mt-6 rounded-2xl border bg-card p-5 shadow-soft">
            <h2 id="team-roles" className="font-display text-lg font-bold">
              {t("team.rolesTitle")}
            </h2>
            <ul className="mt-3 divide-y">
              {ROLES.map((role) => {
                const mine = role === org.my_role;
                return (
                  <li key={role} aria-current={mine ? "true" : undefined} className={cn("flex flex-col gap-1 py-3 sm:flex-row sm:items-start sm:gap-4", mine && "-mx-2 rounded-lg bg-primary/5 px-2")}>
                    <div className="flex shrink-0 items-center gap-2 sm:w-52">
                      <RoleBadge role={role} />
                      {mine && <span className="text-xs font-semibold text-primary">{t("team.yourRole")}</span>}
                    </div>
                    <p className="text-sm text-muted-foreground">{t(`role.${role}_desc`)}</p>
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}
    </OrganizationPage>
  );
};

export default OrganizationTeam;
