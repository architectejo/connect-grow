import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Camera, Handshake, MapPin, MessageSquare, Search, Star, UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";

// Parcours A (vendre) et B (acheter) du cahier des charges, section 6.2
const journeys = {
  buy: { icons: [MapPin, Star, MessageSquare, Handshake] },
  sell: { icons: [UserCheck, Camera, Search, Star] },
} as const;

type Journey = keyof typeof journeys;

const HowItWorksSection = () => {
  const { t } = useTranslation();
  const [journey, setJourney] = useState<Journey>("buy");

  return (
    <section id="comment-ca-marche" className="bg-secondary/50 py-16 md:py-24">
      <div className="container">
        <div className="mx-auto mb-8 max-w-2xl text-center">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">{t("landing.how.eyebrow")}</p>
          <h2 className="mt-2 text-3xl font-extrabold md:text-4xl">{t("landing.how.title")}</h2>
        </div>

        <div role="tablist" aria-label={t("landing.how.journeysLabel")} className="mx-auto mb-10 flex w-fit rounded-full border bg-card p-1 shadow-soft">
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
              {t(`landing.how.${key}.label`)}
            </button>
          ))}
        </div>

        <ol key={journey} className="grid animate-fade-in gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {journeys[journey].icons.map((Icon, index) => (
            <li key={index} className="relative rounded-2xl border bg-card p-6 shadow-soft">
              <span className="absolute right-5 top-4 font-display text-4xl font-extrabold text-foreground/10" aria-hidden>
                {index + 1}
              </span>
              <span className="flex h-11 w-11 items-center justify-center rounded-xl gradient-primary text-primary-foreground shadow-glow">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <h3 className="mt-5 font-bold">{t(`landing.how.${journey}.step${index + 1}Title`)}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{t(`landing.how.${journey}.step${index + 1}Text`)}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
};

export default HowItWorksSection;
