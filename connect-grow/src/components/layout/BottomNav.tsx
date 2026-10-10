import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Home, MessageSquare, Plus, Search, UserRound } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { loginPath } from "@/lib/auth-paths";
import { cn } from "@/lib/utils";

// Pages plein écran sans barre du bas (formulaires d'authentification)
const HIDDEN_ON = ["/login", "/register", "/forgot-password"];
// Pages qui affichent leur propre barre d'action en bas d'écran : on ne garde que l'espace réservé
const OWN_ACTION_BAR = ["/post/", "/create-post", "/edit-post/"];

/**
 * Barre de navigation basse, mobile uniquement : les 5 destinations clés à portée de pouce.
 * Rend aussi un espace réservé en fin de page pour que le contenu ne passe pas dessous.
 */
export function BottomNav() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const { isAuthenticated } = useAuth();

  if (HIDDEN_ON.includes(pathname)) return null;
  if (OWN_ACTION_BAR.some((prefix) => pathname.startsWith(prefix))) {
    return <div className="h-[calc(5rem+env(safe-area-inset-bottom))] md:hidden" aria-hidden />;
  }

  const requireAuth = (to: string) => (isAuthenticated ? to : loginPath(to));

  const items = [
    { to: "/", label: t("nav.home"), icon: Home, end: true },
    { to: "/marketplace", label: t("nav.explore"), icon: Search },
    { to: requireAuth("/create-post"), label: t("nav.publish"), icon: Plus, primary: true },
    { to: requireAuth("/messages"), label: t("nav.messages"), icon: MessageSquare },
    { to: requireAuth("/dashboard"), label: t("nav.profile"), icon: UserRound },
  ];

  return (
    <>
      <div className="h-[calc(4rem+env(safe-area-inset-bottom))] md:hidden" aria-hidden />
      <nav
        aria-label={t("nav.mainNavigation")}
        className="fixed inset-x-0 bottom-0 z-50 border-t bg-background/95 pb-safe backdrop-blur-lg md:hidden"
      >
        <ul className="mx-auto grid h-16 max-w-md grid-cols-5">
          {items.map(({ to, label, icon: Icon, end, primary }) => (
            <li key={label}>
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "flex h-full flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors",
                    isActive && !primary ? "text-primary" : "text-muted-foreground",
                  )
                }
              >
                {({ isActive }) =>
                  primary ? (
                    <>
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl gradient-primary text-primary-foreground shadow-glow">
                        <Icon className="h-5 w-5" strokeWidth={2.5} aria-hidden />
                      </span>
                      <span className="sr-only">{label}</span>
                    </>
                  ) : (
                    <>
                      <span
                        className={cn(
                          "flex h-7 w-12 items-center justify-center rounded-full transition-colors",
                          isActive && "bg-primary/10",
                        )}
                      >
                        <Icon className="h-5 w-5" strokeWidth={isActive ? 2.5 : 2} aria-hidden />
                      </span>
                      {label}
                    </>
                  )
                }
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </>
  );
}
