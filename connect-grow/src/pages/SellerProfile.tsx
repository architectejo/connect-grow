import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Package, Share2, SearchX } from "lucide-react";
import type { SellerContextType } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/layout/AppShell";
import {
  EmptyState,
  ErrorState,
  PostCard,
  PostGrid,
  PostGridSkeleton,
  RatingBlock,
  SellerTypeBadge,
  UserAvatar,
  VerifiedClaims,
} from "@/components/common";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useAuth } from "@/contexts/AuthContext";
import { usePosts, useSellerProfile, useToggleFavorite } from "@/hooks/use-marketplace";
import { shareLink } from "@/lib/contact";
import { httpStatus } from "@/lib/errors";
import { formatMonthYear } from "@/lib/format";

const TYPES: Record<string, SellerContextType> = { user: "USER", provider: "PROVIDER", organization: "ORGANIZATION" };

/**
 * Page publique d'un vendeur (ADR 0006 §9.7) : personnel, prestataire ou organisation. Elle ne montre ni
 * coordonnées, ni adresse exacte, ni membres (jamais fournis par l'API) ; le contact se fait depuis une offre.
 */
const SellerProfile = () => {
  const { t } = useTranslation();
  const { contextType, id } = useParams();
  const type = TYPES[(contextType ?? "").toLowerCase()];
  const { user } = useAuth();
  const { contexts } = useActiveContext();
  const profile = useSellerProfile(type, id);
  const { data: posts = [], isLoading: postsLoading, isError: postsError, refetch: refetchPosts } = usePosts(
    { seller: id, seller_type: type, ordering: "-created_at" },
    undefined,
    { enabled: !!type && !!id && profile.isSuccess },
  );
  const toggleFavorite = useToggleFavorite();

  if (!type) return <SellerNotFound />;

  if (profile.isLoading) {
    return (
      <AppShell>
        <Skeleton className="h-36 w-full rounded-2xl" />
        <div className="-mt-10 flex items-end gap-4 px-4">
          <Skeleton className="h-24 w-24 rounded-2xl border-4 border-background" />
          <Skeleton className="mb-2 h-6 w-48" />
        </div>
        <PostGridSkeleton count={6} className="mt-10" />
      </AppShell>
    );
  }

  if (profile.isError) {
    if (httpStatus(profile.error) === 404) return <SellerNotFound />;
    return (
      <AppShell>
        <ErrorState onRetry={() => profile.refetch()} isRetrying={profile.isRefetching} />
      </AppShell>
    );
  }

  const seller = profile.data;
  const shape = seller.context_type === "ORGANIZATION" ? "square" : "circle";
  const since = seller.member_since ? t("rating.memberSince", { date: formatMonthYear(seller.member_since) }) : undefined;
  // Mon propre profil : lien de modification vers l'écran qui le gère
  const mine =
    seller.context_type === "USER"
      ? user?.id === seller.context_id
      : contexts.some((c) => c.type === seller.context_type && c.id === seller.context_id);
  const editPath =
    seller.context_type === "ORGANIZATION" ? `/organizations/${seller.context_id}/edit` : seller.context_type === "PROVIDER" ? "/profiles" : "/settings";

  return (
    <AppShell>
      <section className="overflow-hidden rounded-2xl border bg-card shadow-soft">
        <div className="relative h-28 gradient-hero md:h-40" aria-hidden>
          <div className="absolute -right-10 -top-10 h-48 w-48 rounded-full bg-sun/25 blur-3xl" />
        </div>
        <div className="px-5 pb-6 md:px-8">
          <div className="-mt-12 flex flex-col gap-4 md:-mt-14 md:flex-row md:items-end md:justify-between">
            <div className="flex items-end gap-4">
              <UserAvatar src={seller.photo} name={seller.display_name} size="xl" shape={shape} className="ring-4 ring-card" />
              <div className="min-w-0 space-y-1.5 pb-1">
                <h1 className="truncate text-2xl font-extrabold md:text-3xl" title={seller.display_name}>
                  {seller.display_name}
                </h1>
                <SellerTypeBadge contextType={seller.context_type} orgType={seller.org_type} />
              </div>
            </div>

            <div className="flex gap-2">
              {mine && (
                <Button asChild variant="outline">
                  <Link to={editPath}>{t("seller.editMine")}</Link>
                </Button>
              )}
              <Button
                variant="outline"
                size="icon"
                className="h-10 w-10"
                aria-label={t("seller.share")}
                onClick={() => shareLink({ title: t("seller.shareTitle", { name: seller.display_name }), url: window.location.href })}
              >
                <Share2 />
              </Button>
            </div>
          </div>

          <VerifiedClaims claims={seller.verified_claims} summary={seller.verification_summary} className="mt-4" />

          <RatingBlock kind="seller" rating={seller.seller_rating} className="mt-4 sm:max-w-xs" footer={since} />

          {seller.description && (
            <p className="mt-4 max-w-2xl whitespace-pre-line text-sm leading-relaxed text-muted-foreground">{seller.description}</p>
          )}

          <p className="mt-5 flex items-center gap-2 text-sm font-medium">
            <Package className="h-4 w-4 text-muted-foreground" aria-hidden />
            {t("seller.offersCount", { count: seller.active_offers_count })}
          </p>
        </div>
      </section>

      <section aria-labelledby="annonces-titre" className="mt-10">
        <h2 id="annonces-titre" className="mb-5 text-xl font-extrabold md:text-2xl">
          {t("seller.offersTitle")}
        </h2>
        {postsLoading ? (
          <PostGridSkeleton count={6} />
        ) : postsError ? (
          <ErrorState onRetry={() => refetchPosts()} />
        ) : posts.length === 0 ? (
          <EmptyState icon={Package} title={t("seller.noOffers")} />
        ) : (
          <PostGrid>
            {posts.map((post) => (
              <PostCard key={post.id} post={post} hideSeller isFavorite={post.is_favorited} onToggleFavorite={toggleFavorite} />
            ))}
          </PostGrid>
        )}
      </section>
    </AppShell>
  );
};

function SellerNotFound() {
  const { t } = useTranslation();
  return (
    <AppShell>
      <EmptyState
        icon={SearchX}
        title={t("seller.notFound")}
        action={
          <Button asChild variant="outline">
            <Link to="/marketplace">{t("seller.seeMarketplace")}</Link>
          </Button>
        }
      />
    </AppShell>
  );
}

export default SellerProfile;
