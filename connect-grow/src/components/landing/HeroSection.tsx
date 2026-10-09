import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { ArrowRight, MapPin, ShieldCheck, TrendingUp } from "lucide-react";
import heroBg from "@/assets/hero-bg.jpg";

const HeroSection = () => {
  return (
    <section className="relative min-h-[90vh] flex items-center overflow-hidden">
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: `url(${heroBg})` }}
      />
      <div className="absolute inset-0 gradient-hero opacity-85" />

      <div className="container relative z-10 mx-auto px-4 py-24">
        <div className="max-w-2xl space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 border border-primary/20 px-4 py-1.5 text-sm text-primary-foreground/80">
            <ShieldCheck size={14} />
            <span>Paiements sécurisés via Laxpaie</span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold leading-tight text-primary-foreground">
            La place de marché
            <br />
            <span className="bg-clip-text text-transparent" style={{ backgroundImage: "var(--gradient-primary)" }}>
              locale et connectée
            </span>
          </h1>

          <p className="text-lg text-primary-foreground/70 max-w-lg leading-relaxed">
            Achetez, vendez, échangez et soutenez des causes locales. 
            Connecte+ rapproche les particuliers, les entreprises et les ONG de votre ville.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <Button size="lg" asChild className="shadow-primary-glow text-base">
              <Link to="/register">
                Commencer gratuitement
                <ArrowRight className="ml-2" size={18} />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild className="border-primary-foreground/20 text-primary-foreground hover:bg-primary-foreground/10">
              <a href="#features">Découvrir</a>
            </Button>
          </div>

          <div className="flex gap-8 pt-6">
            {[
              { icon: MapPin, label: "Géolocalisé", desc: "Trouvez près de vous" },
              { icon: TrendingUp, label: "Analytics", desc: "Suivez vos performances" },
              { icon: ShieldCheck, label: "Sécurisé", desc: "Transactions protégées" },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary-foreground/10 flex items-center justify-center">
                  <item.icon size={18} className="text-primary-foreground/80" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary-foreground">{item.label}</p>
                  <p className="text-xs text-primary-foreground/50">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
