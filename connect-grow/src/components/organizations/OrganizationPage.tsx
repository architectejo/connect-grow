import type { ReactNode } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { OrganizationInternal } from "@/api/types";
import { AccessDenied, ErrorState } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AccountShell } from "@/components/layout/AccountShell";
import { useOrganization } from "@/hooks/use-organizations";
import { organizationDeniedKey } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

export type OrganizationSection = "overview" | "profile" | "verification" | "team";

function OrganizationTabs({ org, section }: { org: OrganizationInternal; section: OrganizationSection }) {
  const { t } = useTranslation();
  const canEdit = org.capabilities.includes("org.edit_profile");
  const tabs = [
    { key: "overview", to: `/organizations/${org.id}`, end: true },
    // Éditeur et analyste n'ont pas de formulaire : le profil public suffit pour lire
    ...(canEdit ? [{ key: "profile", to: `/organizations/${org.id}/edit`, end: false }] : []),
    { key: "verification", to: `/organizations/${org.id}/verification`, end: false },
    { key: "team", to: `/organizations/${org.id}/team`, end: false },
  ];
  return (
    <nav aria-label={t("org.tabs.aria")} className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 scrollbar-none">
      {tabs.map((tab) => (
        <NavLink
          key={tab.key}
          to={tab.to}
          end={tab.end}
          aria-current={tab.key === section ? "page" : undefined}
          className={cn(
            "shrink-0 rounded-full border px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            tab.key === section ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
          )}
        >
          {t(`org.tabs.${tab.key}`)}
        </NavLink>
      ))}
    </nav>
  );
}

interface OrganizationPageProps {
  section: OrganizationSection;
  /** Contenu, rendu une fois l'organisation chargée et accessible. */
  children: (org: OrganizationInternal) => ReactNode;
  /** Sans sous-menu (formulaire de modification sans onglets). */
  hideTabs?: boolean;
}

/**
 * Gabarit des pages `organizations/:id/*` : charge `OrganizationInternal` et traite les états
 * (chargement, erreur avec « Réessayer », refus DENY_RELATION / DENY_SECURITY / DENY_OBJECT_STATE).
 * L'organisation vient du chemin : le profil actif n'a pas à être celui de l'organisation (ADR 0006 §6.4).
 */
export function OrganizationPage({ section, children, hideTabs }: OrganizationPageProps) {
  const { t } = useTranslation();
  const { id } = useParams();
  const query = useOrganization(id);

  let body: ReactNode;
  if (query.isLoading) {
    body = (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-32 w-full rounded-2xl" />
        <Skeleton className="h-32 w-full rounded-2xl" />
      </div>
    );
  } else if (query.isError) {
    const deniedKey = organizationDeniedKey(query.error);
    body = deniedKey ? (
      <AccessDenied
        description={t(deniedKey)}
        action={
          <Button asChild variant="outline">
            <Link to="/profiles">{t("context.myProfiles")}</Link>
          </Button>
        }
      />
    ) : (
      <ErrorState description={t("org.loadError")} onRetry={() => query.refetch()} isRetrying={query.isFetching} />
    );
  } else if (query.data) {
    body = (
      <>
        {!hideTabs && <OrganizationTabs org={query.data} section={section} />}
        {children(query.data)}
      </>
    );
  }

  return <AccountShell>{body}</AccountShell>;
}
