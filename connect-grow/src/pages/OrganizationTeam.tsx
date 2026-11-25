import { Suspense, lazy, useRef, useState } from "react";
import { UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationRole } from "@/api/types";
import { PageHeader, RoleBadge } from "@/components/common";
import { LeaveOrganizationCard } from "@/components/organizations/OrganizationActions";
import { OrganizationPage } from "@/components/organizations/OrganizationPage";
import { InvitationsPanel, type InvitationsPanelHandle } from "@/components/team/InvitationsPanel";
import { MembersPanel } from "@/components/team/MembersPanel";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { cn } from "@/lib/utils";

// Le dialogue est chargé à l'ouverture, pas avec la page (réseau faible)
const InviteDialog = lazy(() => import("@/components/team/InviteDialog").then((m) => ({ default: m.InviteDialog })));

type TeamTab = "members" | "invitations";

const ROLES: OrganizationRole[] = ["OWNER", "ADMIN", "EDITOR", "ANALYST"];

/**
 * Équipe d'une organisation (L1-01, E6) : membres, changement de rôle, retrait, transfert de propriété.
 * Pour les rôles qui gèrent les membres (`org.manage_members`) : bouton « Inviter une personne » et onglet « Invitations »
 * (requête à l'ouverture de l'onglet seulement). Une seule région `aria-live` annonce le résultat des actions.
 */
const OrganizationTeam = () => {
  const { t } = useTranslation();
  const [announcement, setAnnouncement] = useState("");
  const [rolesOpen, setRolesOpen] = useState(false);
  const [tab, setTab] = useState<TeamTab>("members");
  const [inviteOpen, setInviteOpen] = useState(false);
  const online = useOnlineStatus();
  const inviteButton = useRef<HTMLButtonElement>(null);
  const invitations = useRef<InvitationsPanelHandle>(null);

  const closeInvite = (created: boolean) => {
    setInviteOpen(false);
    if (created) {
      // La nouvelle ligne apparaît dans l'onglet Invitations (rechargé par la création)
      setTab("invitations");
      requestAnimationFrame(() => requestAnimationFrame(() => invitations.current?.focusHeading()));
    } else requestAnimationFrame(() => inviteButton.current?.focus());
  };

  return (
    <OrganizationPage section="team">
      {(org) => {
        const canInvite = org.capabilities.includes("org.manage_members");
        return (
          <div className="mx-auto max-w-4xl">
            <PageHeader
              title={t("team.title")}
              actions={
                canInvite && (
                  <Button ref={inviteButton} type="button" className="min-h-11 w-full md:w-auto" disabled={!online} onClick={() => setInviteOpen(true)}>
                    <UserPlus aria-hidden />
                    {t("team.invite.open")}
                  </Button>
                )
              }
            />
            <div role="status" aria-live="polite" className="sr-only">
              {announcement}
            </div>

            {canInvite ? (
              <Tabs value={tab} onValueChange={(next) => setTab(next as TeamTab)}>
                <TabsList className="mb-4 h-11 w-full sm:w-auto" aria-label={t("team.tabs.label")}>
                  <TabsTrigger value="members" className="min-h-9 flex-1 sm:flex-none">
                    {t("team.tabs.members")}
                  </TabsTrigger>
                  <TabsTrigger value="invitations" className="min-h-9 flex-1 sm:flex-none">
                    {t("team.tabs.invitations")}
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="members">
                  <MembersPanel org={org} onAnnounce={setAnnouncement} />
                </TabsContent>
                <TabsContent value="invitations">
                  <InvitationsPanel ref={invitations} org={org} onAnnounce={setAnnouncement} onInvite={() => setInviteOpen(true)} />
                </TabsContent>
              </Tabs>
            ) : (
              <MembersPanel org={org} onAnnounce={setAnnouncement} />
            )}

            <Suspense fallback={null}>
              {inviteOpen && canInvite && <InviteDialog orgId={org.id} orgName={org.name} online={online} onClose={closeInvite} onAnnounce={setAnnouncement} />}
            </Suspense>

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
        );
      }}
    </OrganizationPage>
  );
};

export default OrganizationTeam;
