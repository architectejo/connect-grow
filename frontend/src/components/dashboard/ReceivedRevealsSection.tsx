import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Loader2, MessageSquare, Phone } from "lucide-react";
import type { RevealChannel } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common";
import { useReceivedReveals } from "@/hooks/use-contact-reveal";
import { formatRelativeDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS: Array<RevealChannel | undefined> = [undefined, "CALL", "WHATSAPP"];

/**
 * « Qui a demandé » : personnes connectées qui ont fait afficher le numéro du vendeur (ADR 0005 §5.5).
 * Nom abrégé, offre et date uniquement : jamais de numéro ni d'identifiant du visiteur.
 */
export function ReceivedRevealsSection() {
  const { t } = useTranslation();
  const [channel, setChannel] = useState<RevealChannel | undefined>(undefined);
  const query = useReceivedReveals(channel);
  const reveals = query.data?.reveals ?? [];

  return (
    <section aria-labelledby="qui-a-demande-titre" className="rounded-2xl border bg-card shadow-soft">
      <div className="space-y-3 border-b p-5 sm:p-6">
        <div>
          <h2 id="qui-a-demande-titre" className="text-lg font-bold">
            {t("receivedReveals.title")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("receivedReveals.description")}</p>
        </div>
        <div role="group" aria-label={t("receivedReveals.filterLabel")} className="flex flex-wrap gap-2">
          {FILTERS.map((value) => (
            <button
              key={value ?? "all"}
              type="button"
              aria-pressed={channel === value}
              onClick={() => setChannel(value)}
              className={cn(
                "rounded-full border px-4 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                channel === value ? "border-primary bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:text-foreground",
              )}
            >
              {value ? t(`receivedReveals.${value}`) : t("receivedReveals.filterAll")}
            </button>
          ))}
        </div>
      </div>

      <div className="p-3 sm:p-4" aria-busy={query.isLoading}>
        {query.isLoading ? (
          <div className="space-y-2" role="status" aria-label={t("receivedReveals.loading")}>
            {[0, 1, 2].map((n) => (
              <Skeleton key={n} className="h-14 w-full rounded-xl" />
            ))}
          </div>
        ) : query.isError ? (
          <ErrorState
            title={t("receivedReveals.loadError")}
            onRetry={() => query.refetch()}
            isRetrying={query.isRefetching}
            className="border-0 py-8"
          />
        ) : reveals.length === 0 ? (
          <EmptyState
            title={channel ? t("receivedReveals.emptyFiltered") : t("receivedReveals.empty")}
            description={channel ? undefined : t("receivedReveals.emptyHint")}
            action={
              channel ? undefined : (
                <Button asChild variant="outline">
                  <Link to="/settings">{t("nav.settings")}</Link>
                </Button>
              )
            }
            className="py-8"
          />
        ) : (
          <>
            <ul className="divide-y">
              {reveals.map((reveal) => {
                const Icon = reveal.channel === "CALL" ? Phone : MessageSquare;
                const channelLabel = t(`receivedReveals.${reveal.channel}`);
                return (
                  <li key={reveal.id} className="flex items-center gap-3 px-2 py-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm">
                        {t("receivedReveals.row", { name: reveal.requester_display_name, channel: channelLabel, title: reveal.offer.title })}
                      </p>
                      <p className="text-xs text-muted-foreground">{formatRelativeDate(reveal.created_at)}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
            {query.hasNextPage && (
              <div className="pt-3 text-center">
                <Button variant="outline" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                  {query.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden />}
                  {t("receivedReveals.loadMore")}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
