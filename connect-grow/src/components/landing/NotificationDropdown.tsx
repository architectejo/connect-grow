import { Link, useNavigate } from "react-router-dom";
import { Bell, CheckCheck } from "lucide-react";
import type { AppNotification } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { NotificationItem } from "@/components/notifications/NotificationItem";
import { useTranslation } from "react-i18next";
import { useNotificationActions, useNotifications } from "@/hooks/use-account";

const PREVIEW_COUNT = 6;

/** Cloche de la barre haute : aperçu des dernières notifications et accès au centre complet. */
const NotificationDropdown = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data: notifications = [] } = useNotifications({ poll: true });
  const { markRead, markAllRead } = useNotificationActions();
  const unread = notifications.filter((n) => !n.is_read).length;

  const open = (notification: AppNotification) => {
    if (!notification.is_read) markRead.mutate(notification.id);
    if (notification.link) navigate(notification.link);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative rounded-full"
          aria-label={unread ? t("notifications.bellLabelUnread", { count: unread }) : t("notifications.bellLabel")}
        >
          <Bell className="!h-5 !w-5" />
          {unread > 0 && (
            <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground ring-2 ring-background">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-sm font-bold">{t("notifications.title")}</h2>
          {unread > 0 && (
            <button
              type="button"
              onClick={() => markAllRead.mutate()}
              className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
            >
              <CheckCheck className="h-3.5 w-3.5" aria-hidden /> {t("notifications.markAllRead")}
            </button>
          )}
        </div>

        {notifications.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <Bell className="mx-auto h-8 w-8 text-muted-foreground/30" aria-hidden />
            <p className="mt-2 text-sm text-muted-foreground">{t("notifications.emptyDropdown")}</p>
          </div>
        ) : (
          <ul className="max-h-96 space-y-0.5 overflow-y-auto p-1.5">
            {notifications.slice(0, PREVIEW_COUNT).map((notification) => (
              <li key={notification.id}>
                <NotificationItem notification={notification} onOpen={open} compact />
              </li>
            ))}
          </ul>
        )}

        <div className="border-t p-2">
          <Button asChild variant="ghost" size="sm" className="w-full">
            <Link to="/notifications">{t("notifications.seeAll")}</Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default NotificationDropdown;
