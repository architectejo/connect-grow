import { lazy, Suspense, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronRight, Clock, Eye, Heart, Lightbulb, MapPin, Pencil, Repeat, SearchX, Share2 } from "lucide-react";
import type { Post } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, ErrorState, PostCard, PostGrid, PriceTag, RatingBlock, SellerCard, StatusBadge } from "@/components/common";
import { ContactActions } from "@/components/post/ContactActions";
import { ContactDialog, ExchangeDialog } from "@/components/post/ContactDialogs";
import { PostGallery } from "@/components/post/PostGallery";
import { ReviewsSection } from "@/components/post/ReviewsSection";
import { useAuth } from "@/contexts/AuthContext";
import { usePost, usePosts, useToggleFavorite } from "@/hooks/use-marketplace";
import { loginPath } from "@/lib/auth-paths";
import { shareLink } from "@/lib/contact";
import { formatCount, formatRelativeDate } from "@/lib/format";
import { getPostBadges, sellerDisplayName } from "@/lib/post";
import { cn } from "@/lib/utils";

// Graphique réservé au vendeur : Recharts (≈100 Ko) n'est téléchargé que par lui
const PostStatsCard = lazy(() => import("@/components/post/PostStatsCard").then((m) => ({ default: m.PostStatsCard })));

const CONDITION_LABELS = { NEUF: "Neuf", OCCASION: "Occasion", RECONDITIONNE: "Reconditionné" } as const;

const safetyTips = [
  "Rencontrez le vendeur dans un lieu public et fréquenté.",
  "Vérifiez l'article avant de payer.",
  "Ne payez jamais d'avance un article que vous n'avez pas vu.",
];

function DetailSkeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_380px]" aria-busy>
      <span className="sr-only" role="status">
        Chargement de l'annonce…
      </span>
      <div className="space-y-4">
        <Skeleton className="aspect-[4/3] w-full rounded-2xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-64 w-full rounded-2xl" />
        <Skeleton className="h-48 w-full rounded-2xl" />
      </div>
    </div>
  );
}

function SimilarPosts({ post }: { post: Post }) {
  const { data = [] } = usePosts({ category: post.category }, 9);
  const toggleFavorite = useToggleFavorite();
  const similar = data.filter((p) => p.id !== post.id).slice(0, 4);
  if (similar.length === 0) return null;

  return (
    <section aria-labelledby="similaires-titre" className="mt-12 border-t pt-10">
      <div className="mb-5 flex items-end justify-between gap-4">
        <h2 id="similaires-titre" className="text-xl font-extrabold md:text-2xl">
          Dans la même catégorie
        </h2>
        <Link to={`/marketplace?category=${post.category}`} className="text-sm font-semibold text-primary hover:underline">
          Tout voir
        </Link>
      </div>
      <PostGrid>
        {similar.map((p) => (
          <PostCard key={p.id} post={p} isFavorite={p.is_favorited} onToggleFavorite={toggleFavorite} />
        ))}
      </PostGrid>
    </section>
  );
}

const PostDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const { data: post, isLoading, isError, error, refetch, isRefetching } = usePost(id);
  const toggleFavorite = useToggleFavorite();
  const [contactOpen, setContactOpen] = useState(false);
  const [exchangeOpen, setExchangeOpen] = useState(false);

  const notFound = (error as { response?: { status?: number } } | null)?.response?.status === 404;

  if (isLoading) {
    return (
      <AppShell>
        <DetailSkeleton />
      </AppShell>
    );
  }

  if (!post) {
    return (
      <AppShell>
        {isError && !notFound ? (
          <ErrorState onRetry={() => refetch()} isRetrying={isRefetching} />
        ) : (
          <EmptyState
            icon={SearchX}
            title="Annonce introuvable"
            description="Elle a peut-être été vendue, mise en pause ou supprimée par son vendeur."
            action={
              <Button asChild>
                <Link to="/marketplace">Voir d'autres annonces</Link>
              </Button>
            }
          />
        )}
      </AppShell>
    );
  }

  const isOwner = !!user && user.id === post.seller?.id;
  const sellerName = sellerDisplayName(post.seller);
  const badges = getPostBadges(post);
  const requireAuth = (open: () => void) => () => (isAuthenticated ? open() : navigate(loginPath(`/post/${post.id}`)));
  const share = () => shareLink({ title: post.title, text: `${post.title} sur Connecte+`, url: window.location.href });

  return (
    <AppShell className="pt-16 md:pt-24">
      {/* Fil d'Ariane (desktop) et retour (mobile) */}
      <nav aria-label="Fil d'Ariane" className="mb-4 hidden items-center gap-1.5 text-sm text-muted-foreground md:flex">
        <Link to="/marketplace" className="hover:text-foreground">
          Marketplace
        </Link>
        {post.category_name && (
          <>
            <ChevronRight className="h-4 w-4" aria-hidden />
            <Link to={`/marketplace?category=${post.category}`} className="hover:text-foreground">
              {post.category_name}
            </Link>
          </>
        )}
        <ChevronRight className="h-4 w-4" aria-hidden />
        <span className="truncate text-foreground" aria-current="page">
          {post.title}
        </span>
      </nav>
      <div className="-mx-4 flex items-center justify-between px-2 py-2 md:hidden">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft aria-hidden /> Retour
        </Button>
        <div className="flex">
          <Button variant="ghost" size="icon" onClick={share} aria-label="Partager">
            <Share2 />
          </Button>
          {!isOwner && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => toggleFavorite(post)}
              aria-pressed={!!post.is_favorited}
              aria-label={post.is_favorited ? "Retirer des favoris" : "Ajouter aux favoris"}
            >
              <Heart className={cn(post.is_favorited && "fill-destructive text-destructive")} />
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px] lg:gap-8">
        <PostGallery post={post} />

        {/* Colonne d'action : résumé, vendeur, conseils */}
        <aside className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <div className="space-y-4 lg:sticky lg:top-24">
            <section className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
              {badges.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1.5">
                  {badges.map((badge) => (
                    <StatusBadge key={badge} kind={badge} size="md" />
                  ))}
                </div>
              )}
              {post.category_name && <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">{post.category_name}</p>}
              <h1 className="mt-1.5 text-balance text-2xl font-extrabold leading-tight">{post.title}</h1>
              <PriceTag amount={post.price} currency={post.currency} negotiable={post.is_price_negotiable} size="lg" className="mt-4" />

              <RatingBlock kind="offer" rating={post.offer_rating} className="mt-4" />

              <div className="mt-4 flex flex-wrap gap-1.5">
                {post.post_type === "SERVICE" && <StatusBadge kind="service" size="md" />}
                {post.condition && <StatusBadge kind={post.condition} size="md" />}
                {post.is_exchangeable && <StatusBadge kind="exchangeable" size="md" />}
              </div>

              <ul className="mt-5 space-y-2 border-t pt-4 text-sm text-muted-foreground">
                <li className="flex items-center gap-2.5">
                  <MapPin className="h-4 w-4 text-primary" aria-hidden /> {post.commune_name ?? "Kinshasa"}, Kinshasa
                </li>
                <li className="flex items-center gap-2.5">
                  <Clock className="h-4 w-4" aria-hidden /> Publiée {formatRelativeDate(post.created_at)}
                </li>
                <li className="flex items-center gap-2.5">
                  <Eye className="h-4 w-4" aria-hidden /> {formatCount(post.views_count)} vue{post.views_count > 1 ? "s" : ""}
                  {!!post.favorites_count && (
                    <>
                      <span aria-hidden>·</span>
                      <Heart className="h-4 w-4" aria-hidden /> {post.favorites_count}
                    </>
                  )}
                </li>
              </ul>

              <div className="mt-5 hidden gap-2 md:flex">
                {isOwner ? (
                  <Button asChild className="flex-1">
                    <Link to={`/edit-post/${post.id}`}>
                      <Pencil aria-hidden /> Modifier mon annonce
                    </Link>
                  </Button>
                ) : (
                  <Button variant="outline" className="flex-1" onClick={() => toggleFavorite(post)} aria-pressed={!!post.is_favorited}>
                    <Heart className={cn(post.is_favorited && "fill-destructive text-destructive")} aria-hidden />
                    {post.is_favorited ? "Dans vos favoris" : "Favori"}
                  </Button>
                )}
                <Button variant="outline" size="icon" className="h-10 w-10 shrink-0" onClick={share} aria-label="Partager l'annonce">
                  <Share2 />
                </Button>
              </div>
            </section>

            {post.seller && (
              <SellerCard
                seller={post.seller}
                rating={post.seller_rating}
                actions={
                  isOwner ? undefined : (
                    <>
                      <ContactActions onMessage={requireAuth(() => setContactOpen(true))} />
                      {post.is_exchangeable && (
                        <Button variant="soft" size="lg" onClick={requireAuth(() => setExchangeOpen(true))}>
                          <Repeat aria-hidden /> Proposer un échange
                        </Button>
                      )}
                    </>
                  )
                }
              />
            )}

            {!isOwner && (
              <section className="rounded-2xl border border-sun/30 bg-sun/5 p-4">
                <h2 className="flex items-center gap-2 text-sm font-bold">
                  <Lightbulb className="h-4 w-4 text-sun" aria-hidden /> Conseils de sécurité
                </h2>
                <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
                  {safetyTips.map((tip) => (
                    <li key={tip} className="flex gap-2">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground" aria-hidden />
                      {tip}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </aside>

        {/* Contenu : description, détails, statistiques, avis */}
        <div className="min-w-0 space-y-6">
          <section aria-labelledby="description-titre" className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
            <h2 id="description-titre" className="text-lg font-bold">
              Description
            </h2>
            <p className="mt-3 whitespace-pre-line leading-relaxed text-foreground/90">{post.description}</p>

            <dl className="mt-6 grid grid-cols-2 gap-3 border-t pt-5 text-sm sm:grid-cols-3">
              {[
                { label: "Type", value: post.post_type === "SERVICE" ? "Service" : "Produit" },
                post.condition && { label: "État", value: CONDITION_LABELS[post.condition] },
                post.category_name && { label: "Catégorie", value: post.category_name },
                post.post_type === "PRODUIT" && post.stock !== undefined && { label: "Quantité", value: String(post.stock) },
                { label: "Devise", value: post.currency === "CDF" ? "Franc congolais" : "Dollar US" },
                { label: "Troc", value: post.is_exchangeable ? "Accepté" : "Non" },
              ]
                .filter((item): item is { label: string; value: string } => !!item)
                .map((item) => (
                  <div key={item.label} className="rounded-xl bg-muted/60 p-3">
                    <dt className="text-xs text-muted-foreground">{item.label}</dt>
                    <dd className="mt-0.5 font-semibold">{item.value}</dd>
                  </div>
                ))}
            </dl>
          </section>

          {isOwner && (
            <Suspense fallback={<Skeleton className="h-72 w-full rounded-2xl" />}>
              <PostStatsCard postId={post.id} />
            </Suspense>
          )}

          <ReviewsSection
            postId={post.id}
            isOwner={isOwner}
            currentUserId={user?.id}
            sellerName={sellerName}
          />
        </div>
      </div>

      <SimilarPosts post={post} />

      {/* Barre d'action mobile, à portée de pouce : remplace la barre de navigation sur cette page (voir BottomNav) */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 px-4 py-3 pb-safe backdrop-blur-lg md:hidden">
        {isOwner ? (
          <Button asChild className="h-12 w-full rounded-xl">
            <Link to={`/edit-post/${post.id}`}>
              <Pencil aria-hidden /> Modifier mon annonce
            </Link>
          </Button>
        ) : (
          <ContactActions layout="bar" onMessage={requireAuth(() => setContactOpen(true))} />
        )}
      </div>

      <ContactDialog post={post} open={contactOpen} onOpenChange={setContactOpen} />
      {post.is_exchangeable && <ExchangeDialog post={post} open={exchangeOpen} onOpenChange={setExchangeOpen} />}
    </AppShell>
  );
};

export default PostDetail;
