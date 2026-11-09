import { useTranslation } from "react-i18next";
import { BadgeCheck, ListFilter, ShieldCheck, TrendingUp } from "lucide-react";

// Les trois réponses de Connecte+ aux problèmes des groupes WhatsApp et Facebook (CDC 1.1),
// plus la vitrine vérifiée des entreprises.
const pillars = [
  {
    icon: ListFilter,
    key: "listings",
    tone: "bg-primary/10 text-primary",
  },
  {
    icon: ShieldCheck,
    key: "reviews",
    tone: "bg-success/10 text-success",
  },
  {
    icon: TrendingUp,
    key: "ranking",
    tone: "bg-sun/15 text-sun",
  },
  {
    icon: BadgeCheck,
    key: "verification",
    tone: "bg-info/10 text-info",
  },
] as const;

const FeaturesSection = () => {
  const { t } = useTranslation();
  return (
  <section id="confiance" className="py-16 md:py-24">
    <div className="container">
      <div className="mx-auto mb-10 max-w-2xl text-center md:mb-14">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">{t("landing.features.eyebrow")}</p>
        <h2 className="mt-2 text-balance text-3xl font-extrabold md:text-4xl">{t("landing.features.title")}</h2>
        <p className="mt-3 text-muted-foreground">
          {t("landing.features.subtitle")}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {pillars.map(({ icon: Icon, key, tone }) => (
          <article key={key} className="rounded-2xl border bg-card p-6 shadow-soft transition-shadow hover:shadow-card">
            <span className={`flex h-12 w-12 items-center justify-center rounded-xl ${tone}`}>
              <Icon className="h-6 w-6" aria-hidden />
            </span>
            <h3 className="mt-5 text-lg font-bold">{t(`landing.features.${key}.title`)}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{t(`landing.features.${key}.description`)}</p>
          </article>
        ))}
      </div>
    </div>
  </section>
  );
};

export default FeaturesSection;
