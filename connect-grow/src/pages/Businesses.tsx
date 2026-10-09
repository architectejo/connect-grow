import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, BadgeCheck, Building2, Loader2, MapPin, Search } from "lucide-react";
import type { PublicBusiness } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, ErrorState, PageHeader, StatusBadge, UserAvatar } from "@/components/common";
import { useBusinesses } from "@/hooks/use-marketplace";
import { cn } from "@/lib/utils";

function useDebounced<T>(value: T, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function BusinessCard({ business }: { business: PublicBusiness }) {
  const name = business.business_name;

  return (
    <article className="group relative flex flex-col rounded-2xl border bg-card p-5 shadow-soft transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-lifted focus-within:ring-2 focus-within:ring-ring">
      <div className="flex items-start gap-4">
        <UserAvatar src={business.logo} name={name} size="lg" shape="square" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-bold group-hover:text-primary">
            <Link to={`/u/${business.id}`} className="outline-none after:absolute after:inset-0 after:content-['']">
              {name}
            </Link>
          </h2>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-muted-foreground">
            <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="truncate">{business.commune_name || business.ville_name || "Kinshasa"}</span>
          </p>
          {business.is_verified && <StatusBadge kind="verified" className="mt-2" />}
        </div>
      </div>

      <p className="mt-4 line-clamp-3 flex-1 text-sm leading-relaxed text-muted-foreground">
        {business.bio || "Cette boutique n'a pas encore ajouté de présentation."}
      </p>

      <div className="mt-5 flex items-center justify-end border-t pt-4 text-sm">
        <span className="flex items-center gap-1 font-semibold text-primary">
          Voir la vitrine <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </span>
      </div>
    </article>
  );
}

const Businesses = () => {
  const [search, setSearch] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const debouncedSearch = useDebounced(search.trim());
  const { t } = useTranslation();
  const { data, isLoading, isError, isFetching, isFetchingNextPage, hasNextPage, fetchNextPage, refetch } = useBusinesses(debouncedSearch);

  const all = data?.businesses ?? [];
  const businesses = verifiedOnly ? all.filter((b) => b.is_verified) : all;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Entreprises"
        title="Les boutiques de Kinshasa"
        description="Commerçants, artisans et prestataires inscrits sur Connecte+. Le badge Vérifié signale une boutique dont les documents ont été contrôlés."
      />

      <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex-1 sm:max-w-md">
          <span className="sr-only">Rechercher une entreprise</span>
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Nom, activité…"
            className="h-12 w-full rounded-xl border bg-card pl-11 pr-4 text-base shadow-soft outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        <div className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-soft">
          <Switch id="verified-only" checked={verifiedOnly} onCheckedChange={setVerifiedOnly} />
          <Label htmlFor="verified-only" className="flex cursor-pointer items-center gap-1.5">
            <BadgeCheck className="h-4 w-4 text-success" aria-hidden /> Vérifiées uniquement
          </Label>
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-60 rounded-2xl" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState onRetry={() => refetch()} isRetrying={isFetching} />
      ) : businesses.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="Aucune entreprise trouvée"
          description={search || verifiedOnly ? "Modifiez votre recherche ou retirez le filtre." : "Les premières boutiques arrivent bientôt."}
          action={
            (search || verifiedOnly) && (
              <Button
                variant="outline"
                onClick={() => {
                  setSearch("");
                  setVerifiedOnly(false);
                }}
              >
                Réinitialiser
              </Button>
            )
          }
        />
      ) : (
        <div className={cn("grid gap-4 transition-opacity sm:grid-cols-2 lg:grid-cols-3", isFetching && "opacity-60")}>
          {businesses.map((business) => (
            <BusinessCard key={business.id} business={business} />
          ))}
        </div>
      )}

      {hasNextPage && !isError && (
        <div className="mt-8 flex justify-center">
          <Button variant="outline" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
            {isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden />}
            {t("businesses.loadMore")}
          </Button>
        </div>
      )}
    </AppShell>
  );
};

export default Businesses;
