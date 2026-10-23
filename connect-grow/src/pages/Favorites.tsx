import { Link } from "react-router-dom";
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
        title="Mes favoris"
        description={favorites.length ? `${favorites.length} annonce${favorites.length > 1 ? "s" : ""} enregistrée${favorites.length > 1 ? "s" : ""}` : undefined}
      />
      <AlwaysPersonalNote className="-mt-4 mb-5" />

      {isLoading ? (
        <PostGridSkeleton count={6} className="lg:grid-cols-3" />
      ) : isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : favorites.length === 0 ? (
        <EmptyState
          icon={Heart}
          title="Aucun favori pour l'instant"
          description="Touchez le cœur d'une annonce pour la retrouver ici et suivre son prix."
          action={
            <Button asChild>
              <Link to="/marketplace">
                <Search aria-hidden /> Parcourir les annonces
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
