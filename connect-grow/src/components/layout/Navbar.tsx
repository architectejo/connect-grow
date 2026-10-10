import { useEffect, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2, Heart, LayoutDashboard, LogOut, Menu, MessageSquare, Plus, Settings, ShoppingBag, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { UserAvatar } from "@/components/common/UserAvatar";
import NotificationDropdown from "@/components/landing/NotificationDropdown";
import { ModeToggle } from "@/components/mode-toggle";
import { ActiveContextBanner, MANAGEMENT_LINKS_READY } from "./ActiveContextBanner";
import { ContextSwitcher } from "./ContextSwitcher";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import { userContactLine } from "@/lib/user-contact";
import { Logo } from "./Logo";

const primaryLinks = [
  { to: "/marketplace", key: "nav.marketplace", icon: ShoppingBag },
  { to: "/businesses", key: "nav.businesses", icon: Building2 },
] as const;

const Navbar = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, isAuthenticated, logout } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const handleLogout = () => {
    logout();
    setMenuOpen(false);
    navigate("/");
  };

  // Le menu du compte montre toujours le nom du compte, jamais celui d'une organisation (le profil actif a sa pastille)
  const displayName = user?.full_name;
  const avatarSrc = user?.photo;

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-[background-color,box-shadow,border-color] duration-300",
        scrolled ? "glass shadow-soft" : "border-b border-transparent bg-background/60 backdrop-blur-sm",
      )}
    >
      <nav className="container flex h-16 items-center justify-between gap-4" aria-label={t("nav.mainNavigation")}>
        <Logo />

        {/* Liens principaux — desktop */}
        <div className="hidden items-center gap-1 md:flex">
          {primaryLinks.map(({ to, key, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-colors",
                  isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" aria-hidden />
              {t(key)}
            </NavLink>
          ))}
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          <div className="hidden md:block">
            <ModeToggle />
          </div>

          {isAuthenticated ? (
            <>
              <Button asChild size="sm" className="hidden shadow-glow md:inline-flex">
                <Link to="/create-post">
                  <Plus aria-hidden />
                  {t("nav.publish")}
                </Link>
              </Button>
              <div className="hidden md:block">
                <ContextSwitcher variant="pill" showManagementLinks={MANAGEMENT_LINKS_READY} />
              </div>
              <NotificationDropdown />
              <Button variant="ghost" size="icon" asChild className="hidden rounded-full md:inline-flex">
                <Link to="/messages" aria-label={t("nav.messages")}>
                  <MessageSquare className="!h-5 !w-5" />
                </Link>
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger className="hidden rounded-full md:block" aria-label={t("nav.profile")}>
                  <UserAvatar src={avatarSrc} name={displayName} size="sm" className="ring-primary/20" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-60 rounded-xl p-1.5">
                  <DropdownMenuLabel className="flex items-center gap-3 font-normal">
                    <UserAvatar src={avatarSrc} name={displayName} size="sm" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-foreground">{displayName}</p>
                      <p className="truncate text-xs text-muted-foreground">{userContactLine(user)}</p>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild className="gap-2 rounded-lg py-2">
                    <Link to="/dashboard">
                      <LayoutDashboard className="h-4 w-4" /> {t("nav.dashboard")}
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild className="gap-2 rounded-lg py-2">
                    <Link to="/favorites">
                      <Heart className="h-4 w-4" /> {t("nav.favorites")}
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild className="gap-2 rounded-lg py-2">
                    <Link to="/settings">
                      <Settings className="h-4 w-4" /> {t("nav.settings")}
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild className="gap-2 rounded-lg py-2">
                    <Link to="/trash">
                      <Trash2 className="h-4 w-4" /> {t("nav.trash")}
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={handleLogout}
                    className="gap-2 rounded-lg py-2 text-destructive focus:bg-destructive/10 focus:text-destructive"
                  >
                    <LogOut className="h-4 w-4" /> {t("nav.logout")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          ) : (
            <>
              <Button variant="ghost" asChild className="hidden md:inline-flex">
                <Link to="/login">{t("nav.login")}</Link>
              </Button>
              <Button asChild size="sm" className="shadow-glow">
                <Link to="/register">{t("nav.register")}</Link>
              </Button>
            </>
          )}

          {/* Menu secondaire — mobile (la navigation principale est dans la barre du bas) */}
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="rounded-full md:hidden" aria-label={t("nav.openMenu")}>
                <Menu className="!h-5 !w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="flex w-[85vw] max-w-sm flex-col gap-0 p-0">
              <SheetHeader className="border-b p-4 text-left">
                <SheetTitle asChild>
                  <div>
                    <Logo />
                  </div>
                </SheetTitle>
              </SheetHeader>

              {isAuthenticated && (
                <div className="flex items-center gap-3 border-b p-4">
                  <UserAvatar src={avatarSrc} name={displayName} size="md" />
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-foreground">{displayName}</p>
                    <p className="truncate text-xs text-muted-foreground">{userContactLine(user)}</p>
                  </div>
                </div>
              )}

              <div className="flex-1 space-y-1 overflow-y-auto p-3">
                {[
                  ...primaryLinks,
                  ...(isAuthenticated
                    ? ([
                        { to: "/dashboard", key: "nav.dashboard", icon: LayoutDashboard },
                        { to: "/favorites", key: "nav.favorites", icon: Heart },
                        { to: "/settings", key: "nav.settings", icon: Settings },
                        { to: "/trash", key: "nav.trash", icon: Trash2 },
                      ] as const)
                    : []),
                ].map(({ to, key, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setMenuOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition-colors",
                        isActive ? "bg-primary/10 text-primary" : "text-foreground hover:bg-secondary",
                      )
                    }
                  >
                    <Icon className="h-5 w-5" aria-hidden />
                    {t(key)}
                  </NavLink>
                ))}

                <div className="flex items-center justify-between rounded-xl px-3 py-2 text-sm font-semibold">
                  {t("nav.theme")}
                  <ModeToggle />
                </div>
              </div>

              <div className="border-t p-4 pb-safe">
                {isAuthenticated ? (
                  <Button variant="ghost" onClick={handleLogout} className="w-full justify-start text-destructive hover:bg-destructive/10 hover:text-destructive">
                    <LogOut aria-hidden /> {t("nav.logout")}
                  </Button>
                ) : (
                  <div className="grid gap-2">
                    <Button asChild variant="outline" onClick={() => setMenuOpen(false)}>
                      <Link to="/login">{t("nav.login")}</Link>
                    </Button>
                    <Button asChild onClick={() => setMenuOpen(false)}>
                      <Link to="/register">{t("nav.register")}</Link>
                    </Button>
                  </div>
                )}
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </nav>
      <ActiveContextBanner />
    </header>
  );
};

export default Navbar;
