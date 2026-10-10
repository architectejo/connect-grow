import type { ReactNode } from "react";
import { Navigate, NavLink, useLocation } from "react-router-dom";
import { BadgeCheck, Bell, Heart, LayoutDashboard, Loader2, MessageSquare, Settings, Trash2, type LucideIcon } from "lucide-react";
import { UserAvatar } from "@/components/common/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useNotifications } from "@/hooks/use-account";
import { loginPath } from "@/lib/auth-paths";
import { cn } from "@/lib/utils";
import { AppShell } from "./AppShell";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  businessOnly?: boolean;
  badge?: "notifications";
}

const items: NavItem[] = [
  { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
  { to: "/favorites", label: "Favoris", icon: Heart },
  { to: "/notifications", label: "Notifications", icon: Bell, badge: "notifications" },
  { to: "/messages", label: "Messages", icon: MessageSquare },
  { to: "/trash", label: "Corbeille", icon: Trash2 },
  { to: "/verification", label: "Vérification", icon: BadgeCheck, businessOnly: true },
  { to: "/settings", label: "Paramètres", icon: Settings },
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
  const { user, isLoading } = useAuth();
  const { data: notifications = [] } = useNotifications();
  const unread = notifications.filter((n) => !n.is_read).length;
  const isBusiness = user?.user_type === "ENTREPRISE";
  const visibleItems = items.filter((item) => !item.businessOnly || isBusiness);
  const displayName = user?.business_profile?.business_name || user?.full_name;

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
          <aside className="hidden lg:block" aria-label="Espace personnel">
            <div className="sticky top-24 space-y-4">
              <div className="flex items-center gap-3 rounded-2xl border bg-card p-3 shadow-soft">
                <UserAvatar src={user?.photo || user?.business_profile?.logo} name={displayName} size="md" />
                <div className="min-w-0">
                  <p className="truncate font-semibold">{displayName ?? (isLoading ? "…" : "")}</p>
                  <p className="text-xs text-muted-foreground">{isBusiness ? "Compte entreprise" : "Compte particulier"}</p>
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
                    {item.label}
                    {renderBadge(item)}
                  </NavLink>
                ))}
              </nav>
            </div>
          </aside>

          <div className="min-w-0">
            <nav aria-label="Espace personnel" className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 scrollbar-none lg:hidden">
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
                  {item.label}
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
                  <Loader2 className="h-8 w-8 animate-spin text-primary" aria-label="Chargement" />
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
