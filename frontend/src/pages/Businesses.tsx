import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, BadgeCheck, Building2, Loader2, MapPin, Search } from "lucide-react";
import type { City, ClaimCode, OrganizationFilters, OrganizationType, PublicOrganization } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, ErrorState, PageHeader, SellerTypeBadge, UserAvatar, VerifiedClaims } from "@/components/common";
import { useCities, useOrganizationDirectory } from "@/hooks/use-marketplace";
import { ORG_TYPES } from "@/lib/organization-form";
import { sellerPath } from "@/lib/post";
import { cn } from "@/lib/utils";

const CLAIM_CODES: ClaimCode[] = ["RCCM_VERIFIED", "NATIONAL_ID_VERIFIED", "REPRESENTATIVE_VERIFIED", "NGO_DECREE_VERIFIED"];
const ALL = "all";

function useDebounced<T>(value: T, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function communeName(cities: City[], communeId: string | null): string | undefined {
  if (!communeId) return undefined;
  for (const city of cities) {
    const commune = city.communes.find((c) => c.id === communeId);
    if (commune) return commune.name;
  }
  return undefined;
}

function OrganizationCard({ organization, cities }: { organization: PublicOrganization; cities: City[] }) {
  const { t } = useTranslation();
  const place = communeName(cities, organization.commune_id) ?? "Kinshasa";

  return (
    <article className="group relative flex flex-col rounded-2xl border bg-card p-5 shadow-soft transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-lifted focus-within:ring-2 focus-within:ring-ring">
      <div className="flex items-start gap-4">
        <UserAvatar src={organization.logo} name={organization.name} size="lg" shape="square" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-bold group-hover:text-primary" title={organization.name}>
            <Link to={sellerPath("ORGANIZATION", organization.id)} className="outline-none after:absolute after:inset-0 after:content-['']">
              {organization.name}
            </Link>
          </h2>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-muted-foreground">
            <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="truncate">{place}</span>
          </p>
          <div className="mt-2 space-y-1.5">
            <SellerTypeBadge contextType="ORGANIZATION" orgType={organization.org_type} compact />
            <VerifiedClaims claims={organization.verified_claims} summary={organization.verification_summary} compact />
          </div>
        </div>
      </div>

      <p className="mt-4 line-clamp-3 flex-1 text-sm leading-relaxed text-muted-foreground">{organization.description || t("directory.noDescription")}</p>

      <div className="mt-5 flex items-center justify-end border-t pt-4 text-sm">
        <span className="flex items-center gap-1 font-semibold text-primary">
          {t("directory.seeProfile")} <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </span>
      </div>
    </article>
  );
}

/**
 * Annuaire des organisations. Tri alphabétique côté serveur : ni la vérification, ni une promotion n'y changent
 * l'ordre (règles 3 et 5). Aucune promotion dans cette liste.
 */
const Businesses = () => {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [orgType, setOrgType] = useState<OrganizationType | "">("");
  const [claim, setClaim] = useState<ClaimCode | "">("");
  const [fullyVerified, setFullyVerified] = useState(false);
  const debouncedSearch = useDebounced(search.trim());
  const { data: cities = [] } = useCities();
  const filters = useMemo<OrganizationFilters>(
    () => ({ search: debouncedSearch, org_type: orgType, claim, fully_verified: fullyVerified }),
    [debouncedSearch, orgType, claim, fullyVerified],
  );
  const { data, isLoading, isError, isFetching, isFetchingNextPage, hasNextPage, fetchNextPage, refetch } = useOrganizationDirectory(filters);

  const organizations = data?.organizations ?? [];
  const filtered = !!(search || orgType || claim || fullyVerified);
  const clear = () => {
    setSearch("");
    setOrgType("");
    setClaim("");
    setFullyVerified(false);
  };

  return (
    <AppShell>
      <PageHeader eyebrow={t("directory.eyebrow")} title={t("directory.title")} description={t("directory.description")} />

      <div className="mb-8 space-y-4">
        <label className="relative block sm:max-w-md">
          <span className="sr-only">{t("directory.searchLabel")}</span>
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            maxLength={100}
            placeholder={t("directory.searchPlaceholder")}
            className="h-12 w-full rounded-xl border bg-card pl-11 pr-4 text-base shadow-soft outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>

        <div role="group" aria-label={t("directory.filterType")} className="flex flex-wrap gap-2">
          {[{ value: "" as const }, ...ORG_TYPES].map(({ value }) => {
            const selected = orgType === value;
            return (
              <button
                key={value || ALL}
                type="button"
                aria-pressed={selected}
                onClick={() => setOrgType(value)}
                className={cn(
                  "min-h-9 rounded-full border px-3.5 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  selected ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
                )}
              >
                {value ? t(`orgType.${value}`) : t("directory.filterTypeAll")}
              </button>
            );
          })}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="space-y-1.5 sm:w-72">
            <Label htmlFor="directory-claim" className="text-sm font-semibold">
              {t("directory.filterClaim")}
            </Label>
            <Select value={claim || ALL} onValueChange={(value) => setClaim(value === ALL ? "" : (value as ClaimCode))}>
              <SelectTrigger id="directory-claim" className="h-12 rounded-xl bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t("directory.filterClaimAll")}</SelectItem>
                {CLAIM_CODES.map((code) => (
                  <SelectItem key={code} value={code}>
                    {t(`claims.${code}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-soft">
            <Switch id="directory-fully" checked={fullyVerified} onCheckedChange={setFullyVerified} />
            <Label htmlFor="directory-fully" className="flex cursor-pointer items-center gap-1.5">
              <BadgeCheck className="h-4 w-4 text-success" aria-hidden /> {t("directory.filterFully")}
            </Label>
          </div>
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
      ) : organizations.length === 0 && !hasNextPage ? (
        <EmptyState
          icon={Building2}
          title={filtered ? t("directory.empty") : t("directory.emptyFirst")}
          action={
            filtered && (
              <Button variant="outline" onClick={clear}>
                {t("directory.clear")}
              </Button>
            )
          }
        />
      ) : (
        <div className={cn("grid gap-4 transition-opacity sm:grid-cols-2 lg:grid-cols-3", isFetching && !isFetchingNextPage && "opacity-60")}>
          {organizations.map((organization) => (
            <OrganizationCard key={organization.id} organization={organization} cities={cities} />
          ))}
        </div>
      )}

      {hasNextPage && !isError && (
        <div className="mt-8 flex justify-center">
          <Button variant="outline" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
            {isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden />}
            {t("directory.loadMore")}
          </Button>
        </div>
      )}
    </AppShell>
  );
};

export default Businesses;
