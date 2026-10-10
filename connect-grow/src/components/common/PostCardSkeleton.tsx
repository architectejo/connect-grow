import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Squelette aux proportions exactes de PostCard : aucun saut de mise en page au chargement. */
export function PostCardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col overflow-hidden rounded-xl border bg-card", className)} aria-hidden>
      <Skeleton className="aspect-[4/3] rounded-none" />
      <div className="flex flex-col gap-2 p-3 sm:p-4">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-3 w-1/2" />
        <div className="mt-1 flex items-center gap-2 border-t pt-3">
          <Skeleton className="h-7 w-7 rounded-full" />
          <Skeleton className="h-3 flex-1" />
          <Skeleton className="h-3 w-10" />
        </div>
      </div>
    </div>
  );
}

interface PostGridProps {
  children: React.ReactNode;
  className?: string;
}

/** Grille responsive des cartes d'annonce : 2 colonnes sur mobile, jusqu'à 4 sur grand écran. */
export function PostGrid({ children, className }: PostGridProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4", className)}>{children}</div>
  );
}

export function PostGridSkeleton({ count = 8, className }: { count?: number; className?: string }) {
  return (
    <PostGrid className={className}>
      <span className="sr-only" role="status">
        Chargement des annonces…
      </span>
      {Array.from({ length: count }, (_, i) => (
        <PostCardSkeleton key={i} />
      ))}
    </PostGrid>
  );
}
