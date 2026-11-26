import { useCallback, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Briefcase, Building2, Loader2, Plus, UserRound } from "lucide-react";
import { toast } from "sonner";
import type { AvailableContext, ProviderProfile } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AccountShell } from "@/components/layout/AccountShell";
import { EmptyState, ErrorState, PageHeader, RoleBadge, SellerTypeBadge, UserAvatar } from "@/components/common";
import { AwaitingMembershipsSection } from "@/components/profiles/AwaitingMembershipsSection";
import { LegacyOrgNotice } from "@/components/profiles/LegacyOrgNotice";
import { UnavailableOrganizationsSection } from "@/components/profiles/UnavailableOrganizationsSection";
import { ProviderDialog } from "@/components/profiles/ProviderDialog";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useAuth } from "@/contexts/AuthContext";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useActivateProvider, useArchiveProvider, useProvider } from "@/hooks/use-provider";
import { describeApiError } from "@/lib/api-errors";

function ActiveBadgeOrButton({ context, isActive, onActivate }: { context: Pick<AvailableContext, "type" | "id" | "name">; isActive: boolean; onActivate: () => void }) {
  const { t } = useTranslation();
  if (isActive) {
    return (
      <span className="inline-flex min-h-9 items-center rounded-full bg-primary/10 px-3 text-xs font-semibold text-foreground">{t("profiles.isActive")}</span>
    );
  }
  return (
    <Button type="button" variant="outline" size="sm" aria-label={t("profiles.actAsAria", { name: context.name })} onClick={onActivate}>
      {t("profiles.actAs")}
    </Button>
  );
}

// --- Prestataire (E2 §4.4, E8) ---

function ProviderCard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const online = useOnlineStatus();
  const { contexts, active, setActive, switchToPersonal } = useActiveContext();
  const query = useProvider();
  const reactivate = useActivateProvider();
  const archive = useArchiveProvider();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [error, setError] = useState<string>();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const offlineId = useId();
  const profile: ProviderProfile | null | undefined = query.data;
  const providerContext = contexts.find((c) => c.type === "PROVIDER");

  const focusTitle = () => window.setTimeout(() => titleRef.current?.focus(), 0);

  const activateNow = (created: boolean) => {
    // Le serveur renvoie le profil ; le bouton du message propose d'agir sous ce profil (rien n'est basculé sans demande)
    toast.success(t(created ? "profiles.provider.activated" : "profiles.provider.reactivated"), {
      action: providerContext ? { label: t("profiles.actAs"), onClick: () => setActive(providerContext) } : undefined,
    });
    focusTitle();
  };

  const doReactivate = async () => {
    setError(undefined);
    try {
      const { created } = await reactivate.mutateAsync({});
      activateNow(created);
    } catch (err) {
      setError(describeApiError(err));
    }
  };

  const doArchive = async () => {
    setError(undefined);
    try {
      // Désactiver son propre profil actif est un geste explicite : retour au personnel, annoncé par le message ci-dessous
      const wasActive = active.type === "PROVIDER";
      await archive.mutateAsync();
      if (wasActive) switchToPersonal();
      setConfirmArchive(false);
      toast.success(t("profiles.provider.archivedToast"));
      focusTitle();
    } catch (err) {
      setConfirmArchive(false);
      setError(describeApiError(err));
    }
  };

  let body;
  if (query.isLoading) {
    body = <Skeleton className="h-28 rounded-2xl" />;
  } else if (query.isError) {
    body = <ErrorState className="py-8" description={t("profiles.loadError")} onRetry={() => query.refetch()} isRetrying={query.isFetching} />;
  } else if (!profile) {
    body = (
      <>
        <p className="mt-1 text-sm text-muted-foreground">{t("profiles.provider.intro")}</p>
        <Button type="button" className="mt-4" disabled={!online} aria-describedby={!online ? offlineId : undefined} onClick={() => setDialogOpen(true)}>
          <Briefcase aria-hidden /> {t("profiles.provider.activate")}
        </Button>
      </>
    );
  } else if (profile.status === "ARCHIVED") {
    body = (
      <>
        <p className="mt-1 text-sm text-muted-foreground">{t("profiles.provider.archived")}</p>
        <Button type="button" className="mt-4" disabled={!online || reactivate.isPending} aria-describedby={!online ? offlineId : undefined} onClick={() => void doReactivate()}>
          {reactivate.isPending && <Loader2 className="animate-spin" aria-hidden />}
          {t("profiles.provider.reactivate")}
        </Button>
      </>
    );
  } else {
    const isActive = active.type === "PROVIDER";
    body = (
      <>
        <div className="mt-2 flex items-center gap-3">
          <UserAvatar src={providerContext?.photo} name={profile.display_name} size="md" />
          <div className="min-w-0">
            <p className="truncate font-semibold" title={profile.display_name}>
              {profile.display_name}
            </p>
            <SellerTypeBadge contextType="PROVIDER" className="mt-1" />
          </div>
        </div>
        {profile.bio && <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{profile.bio}</p>}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {providerContext && <ActiveBadgeOrButton context={providerContext} isActive={isActive} onActivate={() => setActive(providerContext)} />}
          <Button type="button" variant="outline" size="sm" disabled={!online} aria-describedby={!online ? offlineId : undefined} onClick={() => setDialogOpen(true)}>
            {t("profiles.provider.edit")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={!online}
            aria-describedby={!online ? offlineId : undefined}
            onClick={() => setConfirmArchive(true)}
          >
            {t("profiles.provider.archive")}
          </Button>
        </div>
      </>
    );
  }

  return (
    <section aria-labelledby={titleId} className="rounded-2xl border bg-card p-5 shadow-soft">
      <h2 id={titleId} ref={titleRef} tabIndex={-1} className="flex items-center gap-2 font-display text-lg font-bold outline-none">
        <Briefcase className="h-5 w-5 text-primary" aria-hidden /> {t("profiles.provider.title")}
      </h2>
      {error && (
        <Alert variant="destructive" role="alert" className="mt-3">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {body}
      {!online && (
        <p id={offlineId} className="mt-2 text-xs text-muted-foreground">
          {t("common.offlineAction")}
        </p>
      )}

      <ProviderDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        profile={profile}
        accountName={user?.full_name ?? ""}
        onDone={(_saved, created) => {
          if (created) activateNow(true);
          else focusTitle();
        }}
      />

      <AlertDialog open={confirmArchive} onOpenChange={(next) => !archive.isPending && setConfirmArchive(next)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("profiles.provider.archiveTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("profiles.provider.archiveDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={archive.isPending}>{t("common.cancel")}</AlertDialogCancel>
            <Button type="button" variant="destructive" disabled={archive.isPending} onClick={() => void doArchive()}>
              {archive.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t("profiles.provider.archiveConfirm")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}

// --- Page ---

const Profiles = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const online = useOnlineStatus();
  const { contexts, unavailable, active, setActive, isLoading, isError, refetch } = useActiveContext();
  const organizations = contexts.filter((c) => c.type === "ORGANIZATION");
  const personal = contexts.find((c) => c.type === "USER");
  const createOffline = !online;
  const orgsTitleId = useId();
  const personalTitleId = useId();
  const orgsTitleRef = useRef<HTMLHeadingElement>(null);
  const personalTitleRef = useRef<HTMLHeadingElement>(null);
  // Région d'annonce unique de la page (E17) : jamais un code ni un indice de téléphone
  const [announcement, setAnnouncement] = useState("");
  const focusOrganizations = useCallback(() => (orgsTitleRef.current ?? personalTitleRef.current)?.focus(), []);

  return (
    <AccountShell>
      <PageHeader
        eyebrow={t("profiles.eyebrow")}
        title={t("profiles.title")}
        description={t("profiles.description")}
        actions={
          createOffline ? (
            <Button type="button" disabled aria-describedby="profiles-offline">
              <Plus aria-hidden /> {t("context.createOrg")}
            </Button>
          ) : (
            <Button asChild>
              <Link to="/organizations/new">
                <Plus aria-hidden /> {t("context.createOrg")}
              </Link>
            </Button>
          )
        }
      />
      {createOffline && (
        <p id="profiles-offline" className="-mt-4 mb-4 text-xs text-muted-foreground">
          {t("common.offlineAction")}
        </p>
      )}

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <LegacyOrgNotice />

      {isLoading && contexts.length === 0 ? (
        <div className="space-y-4" aria-busy="true">
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-24 rounded-2xl" />
        </div>
      ) : isError && contexts.length === 0 ? (
        <ErrorState description={t("profiles.loadError")} onRetry={refetch} />
      ) : (
        <div className="space-y-6">
          <section aria-labelledby={personalTitleId} className="rounded-2xl border bg-card p-5 shadow-soft">
            <h2 id={personalTitleId} ref={personalTitleRef} tabIndex={-1} className="flex items-center gap-2 font-display text-lg font-bold outline-none">
              <UserRound className="h-5 w-5 text-primary" aria-hidden /> {t("profiles.personal.title")}
            </h2>
            <div className="mt-2 flex items-center gap-3">
              <UserAvatar src={user?.photo} name={user?.full_name} size="md" />
              <div className="min-w-0">
                <p className="truncate font-semibold">{user?.full_name}</p>
                <p className="text-xs text-muted-foreground">{t("profiles.personal.hint")}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {personal && <ActiveBadgeOrButton context={personal} isActive={active.type === "USER"} onActivate={() => setActive(personal)} />}
              <Button asChild variant="ghost" size="sm">
                <Link to="/settings">{t("profiles.personal.edit")}</Link>
              </Button>
            </div>
          </section>

          <ProviderCard />

          {/* Sans organisation active mais avec des organisations indisponibles, l'état vide serait contradictoire : on masque la section */}
          {(organizations.length > 0 || unavailable.length === 0) && (
          <section aria-labelledby={orgsTitleId} className="space-y-3">
            <h2 id={orgsTitleId} ref={orgsTitleRef} tabIndex={-1} className="flex items-center gap-2 font-display text-lg font-bold outline-none">
              <Building2 className="h-5 w-5 text-primary" aria-hidden /> {t("profiles.orgs.title")}
            </h2>
            {organizations.length === 0 ? (
              <EmptyState
                icon={Building2}
                title={t("profiles.orgs.emptyTitle")}
                description={t("profiles.orgs.emptyDescription")}
                action={
                  createOffline ? undefined : (
                    <Button asChild>
                      <Link to="/organizations/new">
                        <Plus aria-hidden /> {t("context.createOrg")}
                      </Link>
                    </Button>
                  )
                }
              />
            ) : (
              <ul className="grid gap-3">
                {organizations.map((organization) => (
                  <li key={organization.id}>
                    <article className="relative flex flex-col gap-3 rounded-2xl border bg-card p-4 shadow-soft focus-within:ring-2 focus-within:ring-ring sm:flex-row sm:items-center">
                      <UserAvatar src={organization.photo} name={organization.name} size="md" shape="square" />
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate font-semibold" title={organization.name}>
                          <Link
                            to={`/organizations/${organization.id}`}
                            aria-label={t("profiles.orgs.open", { name: organization.name })}
                            className="outline-none after:absolute after:inset-0 after:content-['']"
                          >
                            {organization.name}
                          </Link>
                        </h3>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          <SellerTypeBadge contextType="ORGANIZATION" orgType={organization.org_type} />
                          {organization.role && <RoleBadge role={organization.role} />}
                        </div>
                      </div>
                      <div className="relative z-10">
                        <ActiveBadgeOrButton
                          context={organization}
                          isActive={active.type === "ORGANIZATION" && active.id === organization.id}
                          onActivate={() => setActive(organization)}
                        />
                      </div>
                    </article>
                  </li>
                ))}
              </ul>
            )}
          </section>
          )}

          <AwaitingMembershipsSection onAnnounce={setAnnouncement} onFocusFallback={focusOrganizations} />

          <UnavailableOrganizationsSection />
        </div>
      )}
    </AccountShell>
  );
};

export default Profiles;
