import { Bell, MessageSquare, Repeat, ShieldCheck, Star, UserRoundSearch, type LucideIcon } from "lucide-react";
import type { AppNotification, NotificationType } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { formatRelativeDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const TYPE_STYLE: Record<NotificationType, { icon: LucideIcon; tone: string; label: string }> = {
  CONTACT: { icon: UserRoundSearch, tone: "bg-primary/10 text-primary", label: "Contact" },
  MESSAGE: { icon: MessageSquare, tone: "bg-info/10 text-info", label: "Message" },
  COMMENT: { icon: Star, tone: "bg-sun/15 text-sun", label: "Avis" },
  EXCHANGE: { icon: Repeat, tone: "bg-success/10 text-success", label: "Troc" },
  SYSTEM: { icon: ShieldCheck, tone: "bg-muted text-muted-foreground", label: "Connecte+" },
};

export const notificationStyle = (type: NotificationType) => TYPE_STYLE[type] ?? { icon: Bell, tone: "bg-muted text-muted-foreground", label: "" };

interface NotificationItemProps {
  notification: AppNotification;
  onOpen: (notification: AppNotification) => void;
  compact?: boolean;
}

/** Une notification : icône par type, titre, extrait, date, pastille « non lue ». */
export function NotificationItem({ notification, onOpen, compact }: NotificationItemProps) {
  const { icon: Icon, tone, label } = notificationStyle(notification.notification_type);

  return (
    <button
      type="button"
      onClick={() => onOpen(notification)}
      className={cn(
        "flex w-full items-start gap-3 text-left transition-colors hover:bg-muted/60",
        compact ? "rounded-lg p-2.5" : "rounded-xl p-4",
        !notification.is_read && "bg-primary/[0.04]",
      )}
    >
      <span className={cn("flex shrink-0 items-center justify-center rounded-xl", compact ? "h-9 w-9" : "h-10 w-10", tone)}>
        <Icon className="h-[18px] w-[18px]" aria-hidden />
        <span className="sr-only">{label}</span>
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-sm", notification.is_read ? "font-medium text-foreground/80" : "font-bold text-foreground")}>
          {notification.title}
        </span>
        <span className={cn("block text-sm text-muted-foreground", compact ? "line-clamp-1" : "line-clamp-2")}>{notification.content}</span>
        {notification.context?.name && (
          // Étiquette du profil concerné : le clic ouvre la cible sans changer le profil actif
          <Badge variant="outline" className="mt-1 max-w-full">
            <span className="truncate">{notification.context.name}</span>
          </Badge>
        )}
        <time dateTime={notification.created_at} className="mt-1 block text-xs text-muted-foreground">
          {formatRelativeDate(notification.created_at)}
        </time>
      </span>
      {!notification.is_read && (
        <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-primary" aria-label="Non lue" />
      )}
    </button>
  );
}
