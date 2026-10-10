import { Link } from "react-router-dom";
import { Compass, Home, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AppShell } from "@/components/layout/AppShell";

const NotFound = () => (
  <AppShell>
    <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center md:py-24">
      <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Compass className="h-8 w-8" aria-hidden />
      </span>
      <p className="mt-6 font-display text-6xl font-extrabold text-foreground/15">404</p>
      <h1 className="mt-2 text-2xl font-extrabold">Cette page n'existe pas</h1>
      <p className="mt-2 text-muted-foreground">Le lien est peut-être incorrect, ou la page a été déplacée.</p>
      <div className="mt-8 flex flex-col gap-2 sm:flex-row">
        <Button asChild>
          <Link to="/">
            <Home aria-hidden /> Accueil
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/marketplace">
            <Search aria-hidden /> Parcourir les annonces
          </Link>
        </Button>
      </div>
    </div>
  </AppShell>
);

export default NotFound;
