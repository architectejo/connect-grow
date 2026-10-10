import type { ReactNode } from "react";
import FooterSection from "@/components/landing/FooterSection";
import { cn } from "@/lib/utils";
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
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main id="contenu" className={cn("flex-1", !bare && "container pb-12 pt-20 md:pt-24", className)}>
        {children}
      </main>
      {withFooter && <FooterSection />}
    </div>
  );
}
