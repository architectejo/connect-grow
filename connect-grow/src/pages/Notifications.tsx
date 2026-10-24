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
import { useTranslation } from "react-i18next";
import { useFeatures } from "@/hooks/use-features";
import { contextFilterOptions, filterNotifications, type NotificationContextFilter } from "@/lib/notifications";
import { cn } from "@/lib/utils";

const groupKey = (date: Date) =>
  isToday(date) ? "today" : isYesterday(date) ? "yesterday" : isThisWeek(date, { weekStartsOn: 1 }) ? "week" : "older";

/** Centre de notifications (CDC 3.6) : état lu / non lu, regroupement par date. */
const Notifications = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { exchangeEnabled } = useFeatures();
  const { data: notifications = [], isLoading, isError, refetch } = useNotifications();
  const { markRead, markAllRead } = useNotificationActions();
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [contextFilter, setContextFilter] = useState<NotificationContextFilter>("all");

  const unread = notifications.filter((n) => !n.is_read).length;
  const contextOptions = contextFilterOptions(notifications);
  // Le profil filtré peut disparaître de la liste (notifications purgées) : retour à « tous les profils »
  const activeContextFilter = contextOptions.some((option) => option.value === contextFilter) ? contextFilter : "all";
  const visible = filterNotifications(notifications, { unreadOnly: filter === "unread", context: activeContextFilter });
  const groups = visible.reduce<{ label: string; items: AppNotification[] }[]>((acc, notification) => {
    const label = t(`notifications.group.${groupKey(new Date(notification.created_at))}`);
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
        title={t("notifications.title")}
        description={unread ? t("notifications.unread", { count: unread }) : t("notifications.upToDate")}
        actions={
          unread > 0 && (
            <Button variant="outline" onClick={() => markAllRead.mutate()} disabled={markAllRead.isPending}>
              <CheckCheck aria-hidden /> {t("notifications.markAllRead")}
            </Button>
          )
        }
      />

      <div role="radiogroup" aria-label={t("notifications.filterLabel")} className="mb-3 flex w-fit rounded-lg bg-muted p-1">
        {[
          { value: "all" as const, label: t("notifications.filterAll") },
          { value: "unread" as const, label: unread ? t("notifications.filterUnreadCount", { count: unread }) : t("notifications.filterUnread") },
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

      {contextOptions.length > 0 && (
        <div className="mb-5 max-w-xs">
          <label htmlFor="notification-context-filter" className="mb-1 block text-xs font-semibold text-muted-foreground">
            {t("notifications.context.filterLabel")}
          </label>
          <select
            id="notification-context-filter"
            value={activeContextFilter}
            onChange={(event) => setContextFilter(event.target.value as NotificationContextFilter)}
            className="h-10 w-full rounded-lg border bg-card px-3 text-sm"
          >
            {contextOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}

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
          title={
            activeContextFilter !== "all"
              ? t("notifications.emptyContext")
              : filter === "unread"
                ? t("notifications.emptyUnread")
                : t("notifications.emptyAll")
          }
          description={exchangeEnabled ? t("exchange.notificationsEmpty") : t("exchange.notificationsEmptyNoExchange")}
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
