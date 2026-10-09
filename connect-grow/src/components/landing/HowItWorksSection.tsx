import { useState } from "react";
import { Camera, Handshake, MapPin, MessageSquare, Search, Star, UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";

// Parcours A (vendre) et B (acheter) du cahier des charges, section 6.2
const journeys = {
  buy: {
    label: "J'achète",
    steps: [
      { icon: MapPin, title: "Cherchez dans votre commune", description: "Filtrez par catégorie, prix, état et commune." },
      { icon: Star, title: "Vérifiez le vendeur", description: "Consultez son Trust Score et les avis de ses clients." },
      { icon: MessageSquare, title: "Contactez-le", description: "Par message, en un geste." },
      { icon: Handshake, title: "Concluez et notez", description: "Votre avis aide toute la communauté à choisir." },
    ],
  },
  sell: {
    label: "Je vends",
    steps: [
      { icon: UserCheck, title: "Créez votre compte", description: "Un numéro +243 vérifié par SMS suffit." },
      { icon: Camera, title: "Publiez gratuitement", description: "Photos, prix en USD ou CDF, commune : c'est prêt." },
      { icon: Search, title: "Soyez trouvé", description: "Les acheteurs de votre ville voient votre annonce." },
      { icon: Star, title: "Gagnez en réputation", description: "Chaque avis positif vous fait monter dans le classement." },
    ],
  },
} as const;

type Journey = keyof typeof journeys;

const HowItWorksSection = () => {
  const [journey, setJourney] = useState<Journey>("buy");

  return (
    <section id="comment-ca-marche" className="bg-secondary/50 py-16 md:py-24">
      <div className="container">
        <div className="mx-auto mb-8 max-w-2xl text-center">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Comment ça marche</p>
          <h2 className="mt-2 text-3xl font-extrabold md:text-4xl">Quatre étapes, pas une de plus</h2>
        </div>

        <div role="tablist" aria-label="Parcours" className="mx-auto mb-10 flex w-fit rounded-full border bg-card p-1 shadow-soft">
          {(Object.keys(journeys) as Journey[]).map((key) => (
            <button
              key={key}
              role="tab"
              type="button"
              aria-selected={journey === key}
              onClick={() => setJourney(key)}
              className={cn(
                "rounded-full px-5 py-2 text-sm font-semibold transition-colors",
                journey === key ? "bg-primary text-primary-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {journeys[key].label}
            </button>
          ))}
        </div>

        <ol key={journey} className="grid animate-fade-in gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {journeys[journey].steps.map(({ icon: Icon, title, description }, index) => (
            <li key={title} className="relative rounded-2xl border bg-card p-6 shadow-soft">
              <span className="absolute right-5 top-4 font-display text-4xl font-extrabold text-foreground/10" aria-hidden>
                {index + 1}
              </span>
              <span className="flex h-11 w-11 items-center justify-center rounded-xl gradient-primary text-primary-foreground shadow-glow">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <h3 className="mt-5 font-bold">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
};

export default HowItWorksSection;
