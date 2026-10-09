import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { CalendarDays, Eye, Package, Phone, Share2, Store } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, ErrorState, PostCard, PostGrid, PostGridSkeleton, StatusBadge, TrustScore, UserAvatar } from "@/components/common";
import { WhatsAppIcon } from "@/components/post/ContactActions";
import { useAuth } from "@/contexts/AuthContext";
import { usePosts, useToggleFavorite } from "@/hooks/use-marketplace";
import { shareLink, telLink, whatsappLink } from "@/lib/contact";
import { formatCount, formatMonthYear } from "@/lib/format";
import { getSellerTrust, sellerDisplayName } from "@/lib/trust";

/**
 * Vitrine publique d'un vendeur ou d'une boutique (CDC 3.1 : profil public).
 * L'API n'expose pas encore de profil utilisateur seul : l'identité vient de ses annonces actives.
 */
const SellerProfile = () => {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: posts = [], isLoading, isError, refetch, isRefetching } = usePosts({ seller: id, ordering: "-created_at" });
  const toggleFavorite = useToggleFavorite();

  const seller = posts[0]?.seller;
  const totalViews = useMemo(() => posts.reduce((sum, p) => sum + (p.views_count ?? 0), 0), [posts]);

  if (isLoading) {
    return (
      <AppShell>
        <Skeleton className="h-36 w-full rounded-2xl" />
        <div className="-mt-10 flex items-end gap-4 px-4">
          <Skeleton className="h-24 w-24 rounded-2xl border-4 border-background" />
          <Skeleton className="mb-2 h-6 w-48" />
        </div>
        <PostGridSkeleton count={8} className="mt-10" />
      </AppShell>
    );
  }

  if (isError) {
    return (
      <AppShell>
        <ErrorState onRetry={() => refetch()} isRetrying={isRefetching} />
      </AppShell>
    );
  }

  if (!seller) {
    return (
      <AppShell>
        <EmptyState
          icon={Store}
          title="Aucune annonce active"
          description="Ce vendeur n'a pas d'annonce en ligne pour le moment."
          action={
            <Button asChild variant="outline">
              <Link to="/marketplace">Parcourir la marketplace</Link>
            </Button>
          }
        />
      </AppShell>
    );
  }

  const name = sellerDisplayName(seller);
  const trust = getSellerTrust(seller);
  const isBusiness = seller.user_type === "ENTREPRISE";
  const isMe = user?.id === seller.id;
  const whatsapp = whatsappLink(seller.phone, `Bonjour, je vous contacte depuis votre vitrine Connecte+.`);
  const call = telLink(seller.phone);

  return (
    <AppShell>
      <section className="overflow-hidden rounded-2xl border bg-card shadow-soft">
        <div className="relative h-28 gradient-hero md:h-40" aria-hidden>
          <div className="absolute -right-10 -top-10 h-48 w-48 rounded-full bg-sun/25 blur-3xl" />
        </div>
        <div className="px-5 pb-6 md:px-8">
          <div className="-mt-12 flex flex-col gap-4 md:-mt-14 md:flex-row md:items-end md:justify-between">
            <div className="flex items-end gap-4">
              <UserAvatar
                src={seller.business_profile?.logo || seller.photo}
                name={name}
                size="xl"
                shape={isBusiness ? "square" : "circle"}
                className="ring-4 ring-card"
              />
              <div className="min-w-0 pb-1">
                <h1 className="truncate text-2xl font-extrabold md:text-3xl">{name}</h1>
                <p className="text-sm text-muted-foreground">{isBusiness ? "Boutique" : "Particulier"}</p>
              </div>
            </div>

            <div className="flex gap-2">
              {isMe ? (
                <Button asChild variant="outline">
                  <Link to="/settings">Modifier mon profil</Link>
                </Button>
              ) : (
                <>
                  {whatsapp && (
                    <Button asChild className="bg-whatsapp text-white hover:bg-whatsapp/90">
                      <a href={whatsapp} target="_blank" rel="noopener noreferrer">
                        <WhatsAppIcon className="!h-5 !w-5" /> WhatsApp
                      </a>
                    </Button>
                  )}
                  {call && (
                    <Button asChild variant="outline" size="icon" className="h-10 w-10">
                      <a href={call} aria-label={`Appeler ${name}`}>
                        <Phone />
                      </a>
                    </Button>
                  )}
                </>
              )}
              <Button
                variant="outline"
                size="icon"
                className="h-10 w-10"
                aria-label="Partager la vitrine"
                onClick={() => shareLink({ title: `${name} sur Connecte+`, url: window.location.href })}
              >
                <Share2 />
              </Button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <TrustScore trust={trust} size="md" />
            {trust.isVerified && <StatusBadge kind="verified" size="md" />}
            {trust.isReliable && <StatusBadge kind="reliable" size="md" />}
          </div>

          {seller.business_profile?.bio && (
            <p className="mt-4 max-w-2xl whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
              {seller.business_profile.bio}
            </p>
          )}

          <dl className="mt-6 grid grid-cols-3 gap-2 sm:max-w-lg">
            {[
              { icon: Package, label: "Annonces", value: String(posts.length) },
              { icon: Eye, label: "Vues", value: formatCount(totalViews) },
              {
                icon: CalendarDays,
                label: "Membre depuis",
                value: seller.date_joined ? formatMonthYear(seller.date_joined) : "—",
              },
            ].map(({ icon: Icon, label, value }) => (
              <div key={label} className="rounded-xl bg-muted/60 p-3">
                <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" aria-hidden /> {label}
                </dt>
                <dd className="mt-1 font-display text-lg font-bold capitalize tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section aria-labelledby="annonces-titre" className="mt-10">
        <h2 id="annonces-titre" className="mb-5 text-xl font-extrabold md:text-2xl">
          Annonces en ligne <span className="text-muted-foreground">({posts.length})</span>
        </h2>
        <PostGrid>
          {posts.map((post) => (
            <PostCard key={post.id} post={post} hideSeller isFavorite={post.is_favorited} onToggleFavorite={toggleFavorite} />
          ))}
        </PostGrid>
      </section>
    </AppShell>
  );
};

export default SellerProfile;
