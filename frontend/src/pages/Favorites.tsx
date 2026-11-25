import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Heart, Search } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import type { Post } from "@/api/types";
import { Button } from "@/components/ui/button";
import { AccountShell } from "@/components/layout/AccountShell";
import { AlwaysPersonalNote } from "@/components/profiles/AlwaysPersonalNote";
import { EmptyState, ErrorState, PageHeader, PostCard, PostGrid, PostGridSkeleton } from "@/components/common";
import { accountKeys, useFavorites } from "@/hooks/use-account";
import { useToggleFavorite } from "@/hooks/use-marketplace";

/** Liste personnelle des favoris (CDC 3.2). */
const Favorites = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: favorites = [], isLoading, isError, refetch } = useFavorites();
  const toggleFavorite = useToggleFavorite();

  // Retrait immédiat de la liste, puis synchronisation avec le serveur
  const remove = (post: Post) => {
    queryClient.setQueryData(accountKeys.favorites, (items: typeof favorites | undefined) =>
      items?.filter((favorite) => favorite.post.id !== post.id),
    );
    toggleFavorite({ ...post, is_favorited: true });
  };

  return (
    <AccountShell>
      <PageHeader
        title={t("favorites.title")}
        description={favorites.length ? t("favorites.saved", { count: favorites.length }) : undefined}
      />
      <AlwaysPersonalNote className="-mt-4 mb-5" />

      {isLoading ? (
        <PostGridSkeleton count={6} className="lg:grid-cols-3" />
      ) : isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : favorites.length === 0 ? (
        <EmptyState
          icon={Heart}
          title={t("favorites.emptyTitle")}
          description={t("favorites.emptyText")}
          action={
            <Button asChild>
              <Link to="/marketplace">
                <Search aria-hidden /> {t("common.browsePosts")}
              </Link>
            </Button>
          }
        />
      ) : (
        <PostGrid className="lg:grid-cols-3">
          {favorites.map(({ id, post }) => (
            <PostCard key={id} post={post} isFavorite onToggleFavorite={remove} />
          ))}
        </PostGrid>
      )}
    </AccountShell>
  );
};

export default Favorites;
