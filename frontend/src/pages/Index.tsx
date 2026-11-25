import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Plus, ShoppingBag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, ErrorState, PostCard, PostGrid, PostGridSkeleton } from "@/components/common";
import HeroSection from "@/components/landing/HeroSection";
import CategoriesSection from "@/components/landing/CategoriesSection";
import FeaturesSection from "@/components/landing/FeaturesSection";
import HowItWorksSection from "@/components/landing/HowItWorksSection";
import SellCtaSection from "@/components/landing/SellCtaSection";
import { usePosts, useToggleFavorite } from "@/hooks/use-marketplace";

const RECOMMENDED_COUNT = 8;

/** Annonces les mieux classées par le classement organique (engagement, récence, proximité). */
const RecommendedPosts = () => {
  const { t } = useTranslation();
  const { data: posts = [], isLoading, isError, refetch, isRefetching } = usePosts(
    { ordering: "-visibility_score" },
    RECOMMENDED_COUNT,
  );
  const toggleFavorite = useToggleFavorite();

  return (
    <section className="py-12 md:py-16">
      <div className="container">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">{t("home.eyebrow")}</p>
            <h2 className="mt-1.5 text-2xl font-extrabold md:text-3xl">{t("home.recommended")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("home.recommendedHint")}</p>
          </div>
          <Button asChild variant="outline" className="hidden shrink-0 sm:inline-flex">
            <Link to="/marketplace">
              {t("common.seeAll")} <ArrowRight aria-hidden />
            </Link>
          </Button>
        </div>

        {isLoading ? (
          <PostGridSkeleton count={RECOMMENDED_COUNT} />
        ) : isError ? (
          <ErrorState onRetry={() => refetch()} isRetrying={isRefetching} />
        ) : posts.length === 0 ? (
          <EmptyState
            icon={ShoppingBag}
            title={t("home.emptyTitle")}
            description={t("home.emptyText")}
            action={
              <Button asChild>
                <Link to="/create-post">
                  <Plus aria-hidden /> {t("common.publishPost")}
                </Link>
              </Button>
            }
          />
        ) : (
          <>
            <PostGrid>
              {posts.map((post) => (
                <PostCard key={post.id} post={post} isFavorite={post.is_favorited} onToggleFavorite={toggleFavorite} />
              ))}
            </PostGrid>
            <Button asChild variant="outline" className="mt-6 w-full sm:hidden">
              <Link to="/marketplace">
                {t("home.seeAll")} <ArrowRight aria-hidden />
              </Link>
            </Button>
          </>
        )}
      </div>
    </section>
  );
};

const Index = () => (
  <AppShell bare>
    <HeroSection />
    <CategoriesSection />
    <RecommendedPosts />
    <FeaturesSection />
    <HowItWorksSection />
    <SellCtaSection />
  </AppShell>
);

export default Index;
