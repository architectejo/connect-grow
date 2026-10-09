import { Link } from "react-router-dom";
import { ArrowRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";

/** Appel à publier : la publication reste gratuite pour tous (CDC 7). */
const SellCtaSection = () => {
  const { isAuthenticated } = useAuth();

  return (
    <section className="py-16 md:py-24">
      <div className="container">
        <div className="relative overflow-hidden rounded-3xl gradient-hero px-6 py-12 text-white shadow-lifted md:px-14 md:py-16">
          <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-sun/25 blur-3xl" aria-hidden />
          <div className="relative flex flex-col items-start gap-8 md:flex-row md:items-center md:justify-between">
            <div className="max-w-xl">
              <h2 className="text-balance text-3xl font-extrabold md:text-4xl">Vous avez quelque chose à vendre ?</h2>
              <p className="mt-3 text-white/75 md:text-lg">
                Publiez votre annonce gratuitement en moins de deux minutes et touchez les acheteurs de votre commune.
              </p>
            </div>
            <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
              <Button asChild size="lg" variant="sun">
                <Link to={isAuthenticated ? "/create-post" : "/register"}>
                  <Plus aria-hidden /> Publier une annonce
                </Link>
              </Button>
              <Button asChild size="lg" variant="ghost" className="text-white hover:bg-white/10 hover:text-white">
                <Link to="/businesses">
                  Espace entreprises <ArrowRight aria-hidden />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default SellCtaSection;
