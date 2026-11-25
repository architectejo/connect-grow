import type { ReactNode } from "react";
import FooterSection from "@/components/landing/FooterSection";
import { useAuth } from "@/contexts/AuthContext";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { cn } from "@/lib/utils";
import { ContextLostAlertHost } from "./ContextLostAlert";
import Navbar from "./Navbar";

interface AppShellProps {
  children: ReactNode;
  /** Pied de page (masqué par défaut sur les écrans applicatifs comme la messagerie). */
  withFooter?: boolean;
  /** Contenu pleine largeur (hero) : pas de conteneur ni de marge sous la barre. */
  bare?: boolean;
  className?: string;
}

/**
 * Gabarit commun des pages : barre haute fixe, contenu, pied de page.
 * La barre du bas mobile et le bandeau hors ligne sont montés une seule fois dans App.
 */
export function AppShell({ children, withFooter = true, bare = false, className }: AppShellProps) {
  const { isAuthenticated } = useAuth();
  const { active, lost } = useActiveContext();
  // Le bandeau du profil actif (h-9) agrandit le header fixe : toujours sur mobile, hors profil personnel sur desktop
  const topPadding = isAuthenticated
    ? cn("pt-[calc(5rem+2.25rem)]", active.type === "USER" ? "md:pt-24" : "md:pt-[calc(6rem+2.25rem)]")
    : "pt-20 md:pt-24";
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main id="contenu" className={cn("flex-1", !bare && cn("container pb-12", topPadding), className)}>
        {lost && bare ? (
          <div className={cn("container", topPadding)}>
            <ContextLostAlertHost />
          </div>
        ) : (
          <ContextLostAlertHost />
        )}
        {children}
      </main>
      {withFooter && <FooterSection />}
    </div>
  );
}
