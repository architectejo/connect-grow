import { useState } from "react";
import { Info, RotateCcw, Trash2 } from "lucide-react";
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
import { AccountShell } from "@/components/layout/AccountShell";
import { ScopeLine } from "@/components/profiles/ScopeLine";
import { useCan } from "@/contexts/ActiveContextContext";
import { EmptyState, ErrorState, ImageWithFallback, PageHeader } from "@/components/common";
import { usePostLifecycle, useTrash } from "@/hooks/use-account";
import { formatPrice } from "@/lib/format";

/** Corbeille (CDC 3.10) : restauration ou suppression définitive ; purge automatique à 30 jours. */
const Trash = () => {
  const { data: posts = [], isLoading, isError, refetch } = useTrash();
  const { restore, destroy } = usePostLifecycle();
  const [deleting, setDeleting] = useState<Post | null>(null);
  // Restaurer ou supprimer : capacités d'édition et de suppression de l'offre (le serveur reste le juge)
  const canEditOffers = useCan("offer.edit");
  const canDeleteOffers = useCan("offer.delete");
  const canManage = canEditOffers || canDeleteOffers;

  return (
    <AccountShell>
      <PageHeader title="Corbeille" description="Les annonces supprimées restent ici 30 jours avant d'être effacées définitivement." />
      <ScopeLine className="-mt-4 mb-5 flex items-center gap-1.5 text-sm text-muted-foreground" />

      <div className="mb-5 flex items-start gap-3 rounded-xl bg-info/10 p-4 text-sm text-foreground">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden />
        Les avis et conversations liés à une annonce supprimée sont conservés.
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-24 rounded-2xl" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : posts.length === 0 ? (
        <EmptyState icon={Trash2} title="La corbeille est vide" description="Les annonces que vous supprimez apparaîtront ici." />
      ) : (
        <ul className="space-y-3">
          {posts.map((post) => (
            <li key={post.id} className="flex flex-col gap-4 rounded-2xl border bg-card p-4 shadow-soft sm:flex-row sm:items-center">
              <div className="flex min-w-0 flex-1 items-center gap-4">
                <ImageWithFallback src={post.main_image} alt="" wrapperClassName="h-16 w-16 shrink-0 rounded-xl opacity-70 grayscale" />
                <div className="min-w-0">
                  <p className="line-clamp-1 font-semibold">{post.title}</p>
                  <p className="text-sm text-muted-foreground">{formatPrice(post.price, post.currency)}</p>
                </div>
              </div>
              {canManage && (
              <div className="flex gap-2 sm:shrink-0">
                <Button
                  variant="outline"
                  className="flex-1 sm:flex-none"
                  onClick={() => restore.mutate(post.id)}
                  disabled={restore.isPending && restore.variables === post.id}
                >
                  <RotateCcw aria-hidden /> Restaurer
                </Button>
                <Button
                  variant="ghost"
                  className="flex-1 text-destructive hover:bg-destructive/10 hover:text-destructive sm:flex-none"
                  onClick={() => setDeleting(post)}
                >
                  <Trash2 aria-hidden /> Supprimer
                </Button>
              </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer définitivement ?</AlertDialogTitle>
            <AlertDialogDescription>
              « {deleting?.title} » sera effacée pour de bon, avec ses photos. Cette action est irréversible.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleting && destroy.mutate(deleting.id)}
            >
              Supprimer définitivement
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AccountShell>
  );
};

export default Trash;
