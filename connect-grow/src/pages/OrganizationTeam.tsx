import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { OrganizationRole } from "@/api/types";
import { PageHeader, RoleBadge } from "@/components/common";
import { LeaveOrganizationCard } from "@/components/organizations/OrganizationActions";
import { OrganizationPage } from "@/components/organizations/OrganizationPage";
import { MembersPanel } from "@/components/team/MembersPanel";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

const ROLES: OrganizationRole[] = ["OWNER", "ADMIN", "EDITOR", "ANALYST"];

/**
 * Équipe d'une organisation (L1-01, E6) : membres, changement de rôle, retrait, transfert de propriété.
 * L'onglet Invitations s'ajoutera à côté de `MembersPanel` (F2). Une seule région `aria-live` annonce le résultat des actions.
 */
const OrganizationTeam = () => {
  const { t } = useTranslation();
  const [announcement, setAnnouncement] = useState("");
  const [rolesOpen, setRolesOpen] = useState(false);
  return (
    <OrganizationPage section="team">
      {(org) => (
        <div className="mx-auto max-w-4xl">
          <PageHeader title={t("team.title")} />
          <div role="status" aria-live="polite" className="sr-only">
            {announcement}
          </div>

          <MembersPanel org={org} onAnnounce={setAnnouncement} />

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
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

          <Collapsible open={rolesOpen} onOpenChange={setRolesOpen} className="mt-6 rounded-2xl border bg-card p-5 shadow-soft">
            <h2 className="font-display text-lg font-bold">
              <CollapsibleTrigger className="flex min-h-11 w-full items-center justify-between text-left">{t("team.rolesTitle")}</CollapsibleTrigger>
            </h2>
            <CollapsibleContent>
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
            </CollapsibleContent>
          </Collapsible>
        </div>
      )}
    </OrganizationPage>
  );
};

export default OrganizationTeam;
