import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useInView } from "react-intersection-observer";
import { ArrowUpDown, Plus, Search, SearchX, SlidersHorizontal, X } from "lucide-react";
import type { PostOrdering, SellerContextType } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, ErrorState, PageHeader, PostCard, PostGrid, PostGridSkeleton } from "@/components/common";
import { ActiveFilters } from "@/components/marketplace/ActiveFilters";
import { FiltersPanel } from "@/components/marketplace/FiltersPanel";
import { DEFAULT_ORDERING, usePostFilters } from "@/components/marketplace/use-post-filters";
import { useCategories, usePosts, useToggleFavorite } from "@/hooks/use-marketplace";
import { isRateLimited, rateLimitMessage } from "@/lib/errors";
import { sellerPath } from "@/lib/post";
import { cn } from "@/lib/utils";

// L'API renvoie toute la liste : on l'affiche par tranches pour ne charger les images qu'au défilement
const PAGE_SIZE = 12;

const orderings: { value: PostOrdering; label: string }[] = [
  { value: "-visibility_score", label: "Recommandées" },
  { value: "-created_at", label: "Plus récentes" },
  { value: "price", label: "Prix croissant" },
  { value: "-price", label: "Prix décroissant" },
];

const Marketplace = () => {
  const { filters, setFilters, resetFilters, activeCount } = usePostFilters();
  const { data: categories = [] } = useCategories();
  const { data: posts = [], isLoading, isError, error, isFetching, refetch } = usePosts(filters);
  const toggleFavorite = useToggleFavorite();

  const [searchInput, setSearchInput] = useState(filters.search ?? "");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [sheetOpen, setSheetOpen] = useState(false);
  const { ref: sentinelRef, inView } = useInView({ rootMargin: "400px" });

  useEffect(() => setSearchInput(filters.search ?? ""), [filters.search]);
  // Nouvelle recherche : on repart de la première tranche
  useEffect(() => setVisibleCount(PAGE_SIZE), [filters]);
  useEffect(() => {
    if (inView && visibleCount < posts.length) setVisibleCount((count) => count + PAGE_SIZE);
  }, [inView, visibleCount, posts.length]);

  // Ancien lien « boutique » : la vitrine d'un vendeur a désormais sa propre page
  if (filters.seller) {
    const type = (filters.seller_type ?? "USER").toUpperCase() as SellerContextType;
    return <Navigate to={sellerPath(["USER", "PROVIDER", "ORGANIZATION"].includes(type) ? type : "USER", filters.seller)} replace />;
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setFilters({ search: searchInput.trim() || undefined });
  };

  const selectedCategory = categories.find((c) => c.id === filters.category);
  const title = filters.search
    ? `Résultats pour « ${filters.search} »`
    : selectedCategory
      ? selectedCategory.name
      : "Toutes les annonces";
  const hasRefinements = activeCount > 0 || !!filters.search;
  const visiblePosts = posts.slice(0, visibleCount);
  const resultLabel = `${posts.length} annonce${posts.length > 1 ? "s" : ""}`;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Marketplace"
        title={title}
        description={isLoading ? "Recherche en cours…" : `${resultLabel} à Kinshasa`}
        className="mb-5"
      />

      {/* Recherche, filtres (mobile) et tri */}
      <div className="flex flex-col gap-2 sm:flex-row">
        <form onSubmit={handleSearch} role="search" className="relative flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Rechercher un produit, un service…"
            aria-label="Rechercher"
            enterKeyHint="search"
            className="h-12 w-full rounded-xl border bg-card pl-11 pr-24 text-base shadow-soft outline-none transition-shadow placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          />
          {searchInput && (
            <button
              type="button"
              onClick={() => {
                setSearchInput("");
                setFilters({ search: undefined });
              }}
              className="absolute right-[4.75rem] top-1/2 -translate-y-1/2 rounded-full p-1.5 text-muted-foreground hover:bg-secondary"
              aria-label="Effacer la recherche"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <Button type="submit" size="sm" className="absolute right-1.5 top-1/2 -translate-y-1/2">
            OK
          </Button>
        </form>

        <div className="flex gap-2">
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" className="h-12 flex-1 rounded-xl bg-card lg:hidden">
                <SlidersHorizontal aria-hidden />
                Filtres
                {activeCount > 0 && (
                  <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[11px] text-primary-foreground">
                    {activeCount}
                  </span>
                )}
              </Button>
            </SheetTrigger>
            <SheetContent side="bottom" className="flex max-h-[88vh] flex-col rounded-t-3xl p-0">
              <SheetHeader className="border-b px-5 py-4 text-left">
                <SheetTitle>Filtres</SheetTitle>
              </SheetHeader>
              <div className="flex-1 overflow-y-auto px-5 py-5">
                <FiltersPanel filters={filters} onChange={setFilters} />
              </div>
              <SheetFooter className="flex-row gap-2 border-t p-4 pb-safe">
                <Button variant="ghost" onClick={resetFilters} disabled={activeCount === 0}>
                  Réinitialiser
                </Button>
                <Button className="flex-1" onClick={() => setSheetOpen(false)}>
                  {isFetching ? "Recherche…" : `Voir ${resultLabel}`}
                </Button>
              </SheetFooter>
            </SheetContent>
          </Sheet>

          <Select
            value={filters.ordering ?? DEFAULT_ORDERING}
            onValueChange={(ordering) => setFilters({ ordering })}
          >
            <SelectTrigger className="h-12 flex-1 gap-2 rounded-xl bg-card shadow-soft sm:w-52 sm:flex-none" aria-label="Trier les annonces">
              <ArrowUpDown className="h-4 w-4 shrink-0 text-primary" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-left">
                <SelectValue />
              </span>
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              {orderings.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Catégories en accès rapide */}
      {categories.length > 0 && (
        <div className="-mx-4 mt-4 flex gap-2 overflow-x-auto px-4 pb-1 scrollbar-none md:mx-0 md:flex-wrap md:px-0">
          {[{ id: "", name: "Toutes" }, ...categories].map((category) => {
            const selected = (filters.category ?? "") === category.id;
            return (
              <button
                key={category.id || "all"}
                type="button"
                aria-pressed={selected}
                onClick={() => setFilters({ category: category.id ? category.id : undefined })}
                className={cn(
                  "shrink-0 rounded-full border px-4 py-2 text-sm font-semibold transition-colors",
                  selected
                    ? "border-foreground bg-foreground text-background"
                    : "bg-card text-muted-foreground hover:border-foreground/30 hover:text-foreground",
                )}
              >
                {category.name}
              </button>
            );
          })}
        </div>
      )}

      <div className="mt-6 grid gap-8 lg:grid-cols-[260px_1fr]">
        <aside className="hidden lg:block" aria-label="Filtres">
          <div className="sticky top-24 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold">Affiner</h2>
              {activeCount > 0 && (
                <button type="button" onClick={resetFilters} className="text-sm font-semibold text-primary hover:underline">
                  Réinitialiser
                </button>
              )}
            </div>
            <FiltersPanel filters={filters} onChange={setFilters} />
          </div>
        </aside>

        <section aria-live="polite" aria-busy={isFetching} className="min-w-0 space-y-4">
          <ActiveFilters filters={filters} onChange={setFilters} onReset={resetFilters} />

          {isLoading ? (
            <PostGridSkeleton count={PAGE_SIZE} className="lg:grid-cols-3" />
          ) : isError ? (
            <ErrorState
              description={isRateLimited(error) ? rateLimitMessage(error) : undefined}
              onRetry={() => refetch()}
              isRetrying={isFetching}
            />
          ) : posts.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title="Aucune annonce ne correspond"
              description={
                hasRefinements
                  ? "Essayez une autre commune, une fourchette de prix plus large ou d'autres mots-clés."
                  : "Aucune annonce n'est publiée pour le moment. Lancez-vous !"
              }
              action={
                hasRefinements ? (
                  <Button variant="outline" onClick={resetFilters}>
                    Élargir la recherche
                  </Button>
                ) : (
                  <Button asChild>
                    <Link to="/create-post">
                      <Plus aria-hidden /> Publier une annonce
                    </Link>
                  </Button>
                )
              }
            />
          ) : (
            <>
              <PostGrid className={cn("lg:grid-cols-3 transition-opacity", isFetching && "opacity-60")}>
                {visiblePosts.map((post) => (
                  <PostCard key={post.id} post={post} isFavorite={post.is_favorited} onToggleFavorite={toggleFavorite} />
                ))}
              </PostGrid>
              {visibleCount < posts.length && (
                <div ref={sentinelRef}>
                  <PostGridSkeleton count={3} className="lg:grid-cols-3" />
                </div>
              )}
              {visibleCount >= posts.length && posts.length > PAGE_SIZE && (
                <p className="py-6 text-center text-sm text-muted-foreground">Vous avez tout vu. {resultLabel} au total.</p>
              )}
            </>
          )}
        </section>
      </div>
    </AppShell>
  );
};

export default Marketplace;
