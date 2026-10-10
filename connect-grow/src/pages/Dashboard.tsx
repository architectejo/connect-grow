import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, BadgeCheck, CalendarDays, Eye, Package, Plus, Star, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AccountShell } from "@/components/layout/AccountShell";
import { MyPostsList } from "@/components/dashboard/MyPostsList";
import { ReceivedRevealsSection } from "@/components/dashboard/ReceivedRevealsSection";
import { ViewsChart } from "@/components/dashboard/ViewsChart";
import { useAuth } from "@/contexts/AuthContext";
import { useDashboardStats, useKycDocuments } from "@/hooks/use-account";
import { useMyPosts } from "@/hooks/use-marketplace";
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

/** Bandeau d'invitation à la vérification pour les comptes entreprise pas encore vérifiés. */
function VerificationBanner() {
  const { data: documents = [] } = useKycDocuments();
  const pending = documents.some((doc) => doc.status === "EN_ATTENTE");

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-success/30 bg-success/5 p-5 sm:flex-row sm:items-center">
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-success/15 text-success">
        <BadgeCheck className="h-6 w-6" aria-hidden />
      </span>
      <div className="flex-1">
        <p className="font-bold">{pending ? "Vérification en cours" : "Obtenez le badge Vérifié"}</p>
        <p className="text-sm text-muted-foreground">
          {pending
            ? "Nos modérateurs examinent vos documents. Vous serez notifié de leur décision."
            : "Les acheteurs font davantage confiance aux boutiques vérifiées. Envoyez votre RCCM et la pièce d'identité du gérant."}
        </p>
      </div>
      <Button asChild variant="outline" className="shrink-0">
        <Link to="/verification">
          {pending ? "Suivre ma demande" : "Commencer"} <ArrowRight aria-hidden />
        </Link>
      </Button>
    </div>
  );
}

const Dashboard = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const stats = useDashboardStats();
  const myPosts = useMyPosts();
  const summary = stats.data?.summary;

  const firstName = user?.full_name?.split(" ")[0];
  const needsVerification = user?.user_type === "ENTREPRISE" && !user.business_profile?.is_verified;
  const reviewCount = summary?.review_count ?? 0;
  // Moyenne des notes vendeur visibles ; privée au vendeur, donc sans seuil d'affichage (null sans avis)
  const avgRating = summary?.avg_rating ?? null;

  return (
    <AccountShell className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Tableau de bord</p>
          <h1 className="mt-1 text-2xl font-extrabold md:text-3xl">Bonjour{firstName ? `, ${firstName}` : ""} 👋</h1>
        </div>
        <Button asChild className="shadow-glow">
          <Link to="/create-post">
            <Plus aria-hidden /> Nouvelle annonce
          </Link>
        </Button>
      </header>

      {needsVerification && <VerificationBanner />}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <StatTile icon={Eye} label="Vues totales" value={formatCount(summary?.total_views)} isLoading={stats.isLoading} />
        <StatTile icon={CalendarDays} label="Vues aujourd'hui" value={formatCount(summary?.today_views)} isLoading={stats.isLoading} />
        <StatTile icon={Package} label="Annonces actives" value={String(summary?.active_posts ?? 0)} isLoading={stats.isLoading} />
        <StatTile
          icon={Star}
          label={t("rating.dashboardLabel")}
          value={avgRating !== null ? formatRating(avgRating) : "—"}
          hint={reviewCount > 0 ? t("rating.count", { count: reviewCount }) : t("rating.none")}
          isLoading={stats.isLoading}
        />
      </div>

      <ViewsChart history={stats.data?.history ?? []} isLoading={stats.isLoading} />

      <MyPostsList
        posts={myPosts.data ?? []}
        isLoading={myPosts.isLoading}
        isError={myPosts.isError}
        onRetry={() => myPosts.refetch()}
      />

      <ReceivedRevealsSection />
    </AccountShell>
  );
};

export default Dashboard;
