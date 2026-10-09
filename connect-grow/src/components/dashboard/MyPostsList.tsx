import { useState } from "react";
import { Link } from "react-router-dom";
import { Eye, ExternalLink, Heart, MoreVertical, Pencil, Plus, Search, Trash2 } from "lucide-react";
import type { Post } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { EmptyState, ErrorState, ImageWithFallback } from "@/components/common";
import { usePostLifecycle } from "@/hooks/use-account";
import { formatCount, formatPrice, formatRelativeDate } from "@/lib/format";

interface MyPostsListProps {
  posts: Post[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

/** Liste « Mes annonces » du tableau de bord vendeur (CDC 3.9). */
export function MyPostsList({ posts, isLoading, isError, onRetry }: MyPostsListProps) {
  const { moveToTrash } = usePostLifecycle();
  const [query, setQuery] = useState("");
  const [trashing, setTrashing] = useState<Post | null>(null);

  const filtered = query.trim()
    ? posts.filter((post) => post.title.toLowerCase().includes(query.trim().toLowerCase()))
    : posts;

  return (
    <section aria-labelledby="mes-annonces-titre" className="rounded-2xl border bg-card shadow-soft">
      <div className="flex flex-col gap-3 border-b p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div>
          <h2 id="mes-annonces-titre" className="text-lg font-bold">
            Mes annonces
          </h2>
          <p className="text-sm text-muted-foreground">{posts.length} annonce{posts.length > 1 ? "s" : ""} en ligne</p>
        </div>
        {posts.length > 4 && (
          <label className="relative sm:w-64">
            <span className="sr-only">Rechercher dans mes annonces</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Rechercher…"
              className="h-10 w-full rounded-lg border bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
        )}
      </div>

      {isLoading ? (
        <ul className="divide-y">
          {[0, 1, 2].map((i) => (
            <li key={i} className="flex items-center gap-4 p-4 sm:px-6">
              <Skeleton className="h-16 w-16 rounded-xl" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            </li>
          ))}
        </ul>
      ) : isError ? (
        <ErrorState onRetry={onRetry} className="m-5 border-0" />
      ) : posts.length === 0 ? (
        <EmptyState
          className="m-5"
          title="Vous n'avez encore rien publié"
          description="Une annonce gratuite, quelques photos, et les acheteurs de votre commune vous trouvent."
          action={
            <Button asChild>
              <Link to="/create-post">
                <Plus aria-hidden /> Publier ma première annonce
              </Link>
            </Button>
          }
        />
      ) : filtered.length === 0 ? (
        <p className="p-8 text-center text-sm text-muted-foreground">Aucune de vos annonces ne contient « {query} ».</p>
      ) : (
        <ul className="divide-y">
          {filtered.map((post) => (
            <li key={post.id} className="flex items-center gap-3 p-4 transition-colors hover:bg-muted/40 sm:gap-4 sm:px-6">
              <Link to={`/post/${post.id}`} className="shrink-0 rounded-xl">
                <ImageWithFallback src={post.main_image} alt="" wrapperClassName="h-16 w-16 rounded-xl sm:h-[72px] sm:w-[72px]" />
              </Link>
              <div className="min-w-0 flex-1">
                <Link to={`/post/${post.id}`} className="line-clamp-1 font-semibold hover:text-primary">
                  {post.title}
                </Link>
                <p className="mt-0.5 font-display text-sm font-bold tabular-nums">{formatPrice(post.price, post.currency)}</p>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Eye className="h-3.5 w-3.5" aria-hidden /> {formatCount(post.views_count)}
                    <span className="sr-only">vues</span>
                  </span>
                  <span className="flex items-center gap-1">
                    <Heart className="h-3.5 w-3.5" aria-hidden /> {post.favorites_count ?? 0}
                    <span className="sr-only">favoris</span>
                  </span>
                  <span>Publiée {formatRelativeDate(post.created_at)}</span>
                </p>
              </div>

              <div className="hidden shrink-0 gap-1 sm:flex">
                <Button asChild variant="ghost" size="icon" aria-label={`Modifier « ${post.title} »`}>
                  <Link to={`/edit-post/${post.id}`}>
                    <Pencil />
                  </Link>
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="hover:bg-destructive/10 hover:text-destructive"
                  onClick={() => setTrashing(post)}
                  aria-label={`Mettre « ${post.title} » à la corbeille`}
                >
                  <Trash2 />
                </Button>
              </div>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="shrink-0 sm:hidden" aria-label={`Actions pour « ${post.title} »`}>
                    <MoreVertical />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="rounded-xl">
                  <DropdownMenuItem asChild className="gap-2">
                    <Link to={`/post/${post.id}`}>
                      <ExternalLink className="h-4 w-4" /> Voir l'annonce
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild className="gap-2">
                    <Link to={`/edit-post/${post.id}`}>
                      <Pencil className="h-4 w-4" /> Modifier
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem className="gap-2 text-destructive focus:text-destructive" onSelect={() => setTrashing(post)}>
                    <Trash2 className="h-4 w-4" /> Mettre à la corbeille
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          ))}
        </ul>
      )}

      <AlertDialog open={!!trashing} onOpenChange={(open) => !open && setTrashing(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Mettre cette annonce à la corbeille ?</AlertDialogTitle>
            <AlertDialogDescription>
                « {trashing?.title} » disparaîtra de la marketplace. Vous pourrez la restaurer depuis la corbeille pendant 30 jours.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => trashing && moveToTrash.mutate(trashing.id)}
            >
              Mettre à la corbeille
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
