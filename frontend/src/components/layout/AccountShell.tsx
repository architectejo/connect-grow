import type { ReactNode } from "react";
import { Navigate, NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BadgeCheck, Bell, Heart, LayoutDashboard, Loader2, MessageSquare, Settings, Trash2, Users, type LucideIcon } from "lucide-react";
import { UserAvatar } from "@/components/common/UserAvatar";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useAuth } from "@/contexts/AuthContext";
import { useNotifications } from "@/hooks/use-account";
import { loginPath } from "@/lib/auth-paths";
import { cn } from "@/lib/utils";
import { AppShell } from "./AppShell";

interface NavItem {
  to: string;
  labelKey: string;
  icon: LucideIcon;
  /** Capacité du profil actif exigée (le serveur reste le juge : le masquage n'est pas le contrôle). */
  capability?: string;
  /** Visible seulement sous un profil organisation. */
  organizationOnly?: boolean;
  badge?: "notifications";
}

const items: NavItem[] = [
  { to: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, capability: "stats.view" },
  { to: "/favorites", labelKey: "nav.favorites", icon: Heart },
  { to: "/notifications", labelKey: "notifications.title", icon: Bell, badge: "notifications" },
  { to: "/messages", labelKey: "nav.messages", icon: MessageSquare, capability: "message.reply" },
  { to: "/trash", labelKey: "nav.trash", icon: Trash2, capability: "offer.view_internal" },
  { to: "/verification", labelKey: "accountNav.verification", icon: BadgeCheck, organizationOnly: true },
  { to: "/profiles", labelKey: "profiles.title", icon: Users },
  { to: "/settings", labelKey: "nav.settings", icon: Settings },
];

/** Réserve une page aux utilisateurs connectés ; les autres passent par la connexion puis reviennent. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) return <Navigate to={loginPath(location.pathname + location.search)} replace />;
  return <>{children}</>;
}

interface AccountShellProps {
  children: ReactNode;
  className?: string;
}

/** Gabarit de l'espace personnel : menu latéral (desktop) ou onglets défilants (mobile). */
export function AccountShell({ children, className }: AccountShellProps) {
  const { t } = useTranslation();
  const { user, isLoading } = useAuth();
  const { active } = useActiveContext();
  const { data: notifications = [] } = useNotifications();
  const unread = notifications.filter((n) => !n.is_read).length;
  const isOrganization = active.type === "ORGANIZATION";
  const visibleItems = items
    .filter((item) => !item.organizationOnly || isOrganization)
    // Capacités pas encore reçues du serveur : on ne masque rien (le serveur refusera de toute façon)
    .filter((item) => !item.capability || !active.confirmed || active.capabilities.includes(item.capability))
    // « Vérification » d'une organisation vit sous son identifiant : /organizations/<id>/verification
    .map((item) => (item.organizationOnly ? { ...item, to: `/organizations/${active.id}/verification` } : item));
  // Le nom du profil actif (organisation ou prestataire), jamais le nom du compte sous un autre profil
  const displayName = active.type === "USER" ? user?.full_name : active.name;
  const typeLabel = active.type === "ORGANIZATION" && active.orgType ? t(`orgType.${active.orgType}`) : t(`context.type.${active.type}`);

  const renderBadge = (item: NavItem) =>
    item.badge === "notifications" && unread > 0 ? (
      <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[11px] font-bold text-destructive-foreground">
        {unread > 99 ? "99+" : unread}
      </span>
    ) : null;

  return (
    <RequireAuth>
      <AppShell withFooter={false}>
        <div className="grid gap-6 lg:grid-cols-[240px_1fr] lg:gap-10">
          <aside className="hidden lg:block" aria-label={t("accountNav.label")}>
            <div className="sticky top-24 space-y-4">
              <div className="flex items-center gap-3 rounded-2xl border bg-card p-3 shadow-soft">
                <UserAvatar src={active.type === "USER" ? user?.photo : active.photo} name={displayName} size="md" shape={isOrganization ? "square" : "circle"} />
                <div className="min-w-0">
                  <p className="truncate font-semibold">{displayName ?? (isLoading ? "…" : "")}</p>
                  <p className="text-xs text-muted-foreground">{typeLabel}</p>
                </div>
              </div>
              <nav className="space-y-0.5">
                {visibleItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors",
                        isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                      )
                    }
                  >
                    <item.icon className="h-[18px] w-[18px]" aria-hidden />
                    {t(item.labelKey)}
                    {renderBadge(item)}
                  </NavLink>
                ))}
              </nav>
            </div>
          </aside>

          <div className="min-w-0">
            <nav aria-label={t("accountNav.label")} className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 scrollbar-none lg:hidden">
              {visibleItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      "flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-semibold transition-colors",
                      isActive ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground",
                    )
                  }
                >
                  <item.icon className="h-4 w-4" aria-hidden />
                  {t(item.labelKey)}
                  {item.badge === "notifications" && unread > 0 && (
                    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-[11px] text-destructive-foreground">
                      {unread}
                    </span>
                  )}
                </NavLink>
              ))}
            </nav>
            <div className={className}>
              {isLoading ? (
                <div className="flex justify-center py-20">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" aria-label={t("states.loading")} />
                </div>
              ) : (
                children
              )}
            </div>
          </div>
        </div>
      </AppShell>
    </RequireAuth>
  );
}
