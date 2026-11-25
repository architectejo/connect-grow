import type { AppNotification } from "@/api/types";
import i18n from "@/i18n";

/** Filtre par profil : toutes, personnelles (`context` nul), ou un profil précis (`TYPE:identifiant`). */
export type NotificationContextFilter = "all" | "personal" | `${"ORGANIZATION" | "PROVIDER"}:${string}`;

type NotificationContext = NonNullable<AppNotification["context"]>;

/** Une notification est personnelle quand `context` est nul (ADR 0006 §9.8) ; un contexte `USER` est traité de même. */
const teamContext = (notification: AppNotification): NotificationContext | null => {
  const context = notification.context;
  return context && context.type !== "USER" ? context : null;
};

const keyOf = (context: NotificationContext) => `${context.type}:${context.id}` as NotificationContextFilter;

/** Libellé du badge d'un profil : « Organisation Atelier X » ; sans nom (profil supprimé) : le type seul. */
export function notificationContextLabel(context: NotificationContext): string {
  const type = context.type === "PROVIDER" ? "PROVIDER" : "ORGANIZATION";
  return context.name ? i18n.t(`notifications.context.${type}`, { name: context.name }) : i18n.t(`notifications.context.${type}_unnamed`);
}

export interface ContextFilterOption {
  value: NotificationContextFilter;
  label: string;
}

/**
 * Options du filtre par profil, construites d'après les notifications reçues : aucune option tant qu'il n'y a que
 * des notifications personnelles (le filtre reste alors masqué).
 */
export function contextFilterOptions(notifications: AppNotification[]): ContextFilterOption[] {
  const profiles = new Map<NotificationContextFilter, NotificationContext>();
  let hasPersonal = false;
  for (const notification of notifications) {
    const context = teamContext(notification);
    if (context) profiles.set(keyOf(context), context);
    else hasPersonal = true;
  }
  if (profiles.size === 0) return [];
  const options: ContextFilterOption[] = [{ value: "all", label: i18n.t("notifications.context.all") }];
  if (hasPersonal) options.push({ value: "personal", label: i18n.t("notifications.context.personal") });
  const named = [...profiles.entries()].map(([value, context]) => ({ value, label: notificationContextLabel(context) }));
  named.sort((a, b) => a.label.localeCompare(b.label, "fr"));
  return [...options, ...named];
}

export function filterNotifications(
  notifications: AppNotification[],
  { unreadOnly = false, context = "all" }: { unreadOnly?: boolean; context?: NotificationContextFilter } = {},
): AppNotification[] {
  return notifications.filter((notification) => {
    if (unreadOnly && notification.is_read) return false;
    if (context === "all") return true;
    const team = teamContext(notification);
    return context === "personal" ? team === null : team !== null && keyOf(team) === context;
  });
}
