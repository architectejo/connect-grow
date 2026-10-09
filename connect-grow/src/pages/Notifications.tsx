import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { isToday, isYesterday, isThisWeek } from "date-fns";
import { BellOff, CheckCheck } from "lucide-react";
import type { AppNotification } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AccountShell } from "@/components/layout/AccountShell";
import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { NotificationItem } from "@/components/notifications/NotificationItem";
import { useNotificationActions, useNotifications } from "@/hooks/use-account";
import { cn } from "@/lib/utils";

const groupLabel = (date: Date) =>
  isToday(date) ? "Aujourd'hui" : isYesterday(date) ? "Hier" : isThisWeek(date, { weekStartsOn: 1 }) ? "Cette semaine" : "Plus ancien";

/** Centre de notifications (CDC 3.6) : état lu / non lu, regroupement par date. */
const Notifications = () => {
  const navigate = useNavigate();
  const { data: notifications = [], isLoading, isError, refetch } = useNotifications();
  const { markRead, markAllRead } = useNotificationActions();
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const unread = notifications.filter((n) => !n.is_read).length;
  const visible = filter === "unread" ? notifications.filter((n) => !n.is_read) : notifications;
  const groups = visible.reduce<{ label: string; items: AppNotification[] }[]>((acc, notification) => {
    const label = groupLabel(new Date(notification.created_at));
    const group = acc.find((g) => g.label === label);
    if (group) group.items.push(notification);
    else acc.push({ label, items: [notification] });
    return acc;
  }, []);

  const open = (notification: AppNotification) => {
    if (!notification.is_read) markRead.mutate(notification.id);
    if (notification.link) navigate(notification.link);
  };

  return (
    <AccountShell>
      <PageHeader
        title="Notifications"
        description={unread ? `${unread} non lue${unread > 1 ? "s" : ""}` : "Vous êtes à jour."}
        actions={
          unread > 0 && (
            <Button variant="outline" onClick={() => markAllRead.mutate()} disabled={markAllRead.isPending}>
              <CheckCheck aria-hidden /> Tout marquer comme lu
            </Button>
          )
        }
      />

      <div role="radiogroup" aria-label="Filtrer" className="mb-5 flex w-fit rounded-lg bg-muted p-1">
        {[
          { value: "all" as const, label: "Toutes" },
          { value: "unread" as const, label: `Non lues${unread ? ` (${unread})` : ""}` },
        ].map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={filter === option.value}
            onClick={() => setFilter(option.value)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-semibold transition-colors",
              filter === option.value ? "bg-card text-foreground shadow-soft" : "text-muted-foreground",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={BellOff}
          title={filter === "unread" ? "Aucune notification non lue" : "Aucune notification"}
          description="Contacts, avis, messages et propositions de troc apparaîtront ici."
        />
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <h2 className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">{group.label}</h2>
              <ul className="divide-y overflow-hidden rounded-2xl border bg-card shadow-soft">
                {group.items.map((notification) => (
                  <li key={notification.id}>
                    <NotificationItem notification={notification} onOpen={open} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </AccountShell>
  );
};

export default Notifications;
