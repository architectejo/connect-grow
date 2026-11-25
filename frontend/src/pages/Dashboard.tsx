import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, CalendarDays, Eye, Info, Package, Plus, ShieldCheck, Star, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AccessDenied, ErrorState } from "@/components/common";
import { AccountShell } from "@/components/layout/AccountShell";
import { LegacyOrgNotice } from "@/components/profiles/LegacyOrgNotice";
import { ScopeLine } from "@/components/profiles/ScopeLine";
import { MyPostsList } from "@/components/dashboard/MyPostsList";
import { ReceivedRevealsSection } from "@/components/dashboard/ReceivedRevealsSection";
import { ViewsChart } from "@/components/dashboard/ViewsChart";
import { useActiveContext, useCan } from "@/contexts/ActiveContextContext";
import { useAuth } from "@/contexts/AuthContext";
import { useDashboardStats } from "@/hooks/use-account";
import { useMyPosts } from "@/hooks/use-marketplace";
import { useOrganization } from "@/hooks/use-organizations";
import { DASHBOARD_CAPABILITY, MY_POSTS_CAPABILITY, isPermissionDenied, lacksCapability } from "@/lib/dashboard";
import { formatCount, formatRating } from "@/lib/format";

interface StatTileProps {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  isLoading?: boolean;
}

function StatTile({ icon: Icon, label, value, hint, isLoading }: StatTileProps) {
  return (
    <div className="rounded-2xl border bg-card p-4 shadow-soft sm:p-5">
      <p className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        {label}
      </p>
      {isLoading ? (
        <Skeleton className="mt-3 h-8 w-20" />
      ) : (
        <p className="mt-3 font-display text-2xl font-extrabold tabular-nums sm:text-3xl">{value}</p>
      )}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/**
 * Rappel de la vérification d'une organisation (profil actif). Le texte décrit des pièces à envoyer, jamais un
 * « badge » à obtenir : la vérification dit ce qui a été examiné, elle ne s'achète pas et ne garantit rien (règle 3).
 */
function VerificationBanner({ organizationId }: { organizationId: string }) {
  const { t } = useTranslation();
  const canSubmit = useCan("org.verification_submit");
  const { data: org } = useOrganization(organizationId);
  if (!org || !canSubmit || org.verification.summary.complete || org.verification.required.length === 0) return null;
  const pending = org.verification.required.some((doc) => doc.state === "EN_ATTENTE");

  return (
    <div className="flex flex-col gap-4 rounded-2xl border bg-card p-5 shadow-soft sm:flex-row sm:items-center">
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <ShieldCheck className="h-6 w-6" aria-hidden />
      </span>
      <div className="flex-1">
        <p className="font-bold">{t(pending ? "dashboard.verificationPendingTitle" : "dashboard.verificationTodoTitle")}</p>
        <p className="text-sm text-muted-foreground">{t(pending ? "dashboard.verificationPendingBody" : "dashboard.verificationTodoBody")}</p>
      </div>
      <Button asChild variant="outline" className="shrink-0">
        <Link to={`/organizations/${organizationId}/verification`}>
          {t(pending ? "dashboard.verificationFollow" : "dashboard.verificationStart")} <ArrowRight aria-hidden />
        </Link>
      </Button>
    </div>
  );
}

/**
 * Profil sans `stats.view` (rôle Membre d'une organisation, contrat L1-01 §7.1) : état explicite avec des sorties utiles,
 * jamais des tuiles muettes ni une erreur à réessayer. Aucun chiffre, aucune offre n'est demandé au serveur.
 */
function RoleRestricted() {
  const { t } = useTranslation();
  const { active } = useActiveContext();
  const isOrganization = active.type === "ORGANIZATION";
  return (
    <AccessDenied
      title={t("dashboardPage.roleRestricted.title")}
      description={active.role === "MEMBER" ? t("dashboardPage.roleRestricted.bodyMember", { name: active.name }) : t("dashboardPage.roleRestricted.body")}
      action={
        <div className="flex flex-col items-stretch justify-center gap-2 sm:flex-row sm:items-center">
          {isOrganization && (
            <Button asChild className="min-h-11">
              <Link to={`/organizations/${active.id}`}>
                {t("dashboardPage.roleRestricted.openOrganization")} <ArrowRight aria-hidden />
              </Link>
            </Button>
          )}
          {isOrganization && (
            <Button asChild variant="outline" className="min-h-11">
              <Link to={`/organizations/${active.id}/team`}>{t("dashboardPage.roleRestricted.team")}</Link>
            </Button>
          )}
          <Button asChild variant={isOrganization ? "ghost" : "default"} className="min-h-11">
            <Link to="/profiles">{t("dashboardPage.roleRestricted.changeProfile")}</Link>
          </Button>
        </div>
      }
    />
  );
}

const Dashboard = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { active } = useActiveContext();
  const canPublish = useCan("offer.publish");
  const canViewRequesters = useCan("contact.view_requesters");
  // Profil confirmé sans la capacité : aucune requête vouée au refus. Sinon, un 403 DENY_PERMISSION reçu mène au même état.
  const noStats = lacksCapability(active, DASHBOARD_CAPABILITY);
  const noPosts = lacksCapability(active, MY_POSTS_CAPABILITY);
  const stats = useDashboardStats(!noStats);
  const myPosts = useMyPosts(!noStats && !noPosts);
  const restricted = noStats || isPermissionDenied(stats.error);
  const postsDenied = noPosts || isPermissionDenied(myPosts.error);
  const summary = stats.data?.summary;

  const firstName = user?.full_name?.split(" ")[0];
  const reviewCount = summary?.review_count ?? 0;
  // Moyenne des notes vendeur visibles ; privée au vendeur, donc sans seuil d'affichage (null sans avis)
  const avgRating = summary?.avg_rating ?? null;

  return (
    <AccountShell className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{t("dashboardPage.eyebrow")}</p>
          <h1 className="mt-1 text-2xl font-extrabold md:text-3xl">{firstName ? t("dashboardPage.greetingNamed", { name: firstName }) : t("dashboardPage.greeting")}</h1>
          {!restricted && <ScopeLine />}
        </div>
        {canPublish && !restricted && (
          <Button asChild className="shadow-glow">
            <Link to="/create-post">
              <Plus aria-hidden /> {t("dashboardPage.newPost")}
            </Link>
          </Button>
        )}
      </header>

      {active.type === "USER" && <LegacyOrgNotice />}
      {active.type === "ORGANIZATION" && !restricted && <VerificationBanner organizationId={active.id} />}

      {restricted ? (
        <RoleRestricted />
      ) : (
        <>
          {stats.isError ? (
            <ErrorState title={t("dashboardPage.statsError")} onRetry={() => void stats.refetch()} isRetrying={stats.isFetching} />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
                <StatTile icon={Eye} label={t("dashboardPage.totalViews")} value={formatCount(summary?.total_views)} isLoading={stats.isLoading} />
                <StatTile icon={CalendarDays} label={t("dashboardPage.todayViews")} value={formatCount(summary?.today_views)} isLoading={stats.isLoading} />
                <StatTile icon={Package} label={t("dashboardPage.activePosts")} value={String(summary?.active_posts ?? 0)} isLoading={stats.isLoading} />
                <StatTile
                  icon={Star}
                  label={t("rating.dashboardLabel")}
                  value={avgRating !== null ? formatRating(avgRating) : "—"}
                  hint={reviewCount > 0 ? t("rating.count", { count: reviewCount }) : t("rating.none")}
                  isLoading={stats.isLoading}
                />
              </div>

              <ViewsChart history={stats.data?.history ?? []} isLoading={stats.isLoading} />
            </>
          )}

          <MyPostsList
            posts={myPosts.data ?? []}
            isLoading={myPosts.isLoading}
            isError={myPosts.isError && !postsDenied}
            isDenied={postsDenied}
            onRetry={() => myPosts.refetch()}
          />

          {canViewRequesters ? (
            <ReceivedRevealsSection />
          ) : (
            // Analyste : les compteurs du tableau de bord suffisent, la liste nominative lui est refusée par le serveur
            <p className="flex items-start gap-2 rounded-xl bg-muted/60 p-4 text-sm text-muted-foreground">
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {t("scope.requestersHidden")}
            </p>
          )}
        </>
      )}
    </AccountShell>
  );
};

export default Dashboard;
