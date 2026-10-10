import { BadgeCheck, ListFilter, ShieldCheck, TrendingUp } from "lucide-react";

// Les trois réponses de Connecte+ aux problèmes des groupes WhatsApp et Facebook (CDC 1.1),
// plus la vitrine vérifiée des entreprises.
const pillars = [
  {
    icon: ListFilter,
    title: "Des annonces qui ne se perdent plus",
    description: "Chaque annonce a sa catégorie, son prix en USD ou en CDF et sa commune. Filtrez en quelques secondes.",
    tone: "bg-primary/10 text-primary",
  },
  {
    icon: ShieldCheck,
    title: "Des avis après contact",
    description:
      "Seules les personnes qui ont contacté le vendeur peuvent noter l'offre et le vendeur, séparément. Il n'y a pas de score unique.",
    tone: "bg-success/10 text-success",
  },
  {
    icon: TrendingUp,
    title: "Un classement transparent",
    description: "Le classement dépend de l'engagement, de la récence et de la proximité, pas des notes. Une annonce sponsorisée est toujours signalée.",
    tone: "bg-sun/15 text-sun",
  },
  {
    icon: BadgeCheck,
    title: "Des boutiques vérifiées",
    description: "Les entreprises présentent leurs documents (RCCM, identité du gérant) pour obtenir le badge Vérifié.",
    tone: "bg-info/10 text-info",
  },
];

const FeaturesSection = () => (
  <section id="confiance" className="py-16 md:py-24">
    <div className="container">
      <div className="mx-auto mb-10 max-w-2xl text-center md:mb-14">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Pourquoi Connecte+</p>
        <h2 className="mt-2 text-balance text-3xl font-extrabold md:text-4xl">Fini les arnaques et les annonces noyées</h2>
        <p className="mt-3 text-muted-foreground">
          Acheter entre particuliers à Kinshasa ne devrait pas être un pari. Connecte+ rend chaque vendeur identifiable et
          chaque annonce facile à trouver.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {pillars.map(({ icon: Icon, title, description, tone }) => (
          <article key={title} className="rounded-2xl border bg-card p-6 shadow-soft transition-shadow hover:shadow-card">
            <span className={`flex h-12 w-12 items-center justify-center rounded-xl ${tone}`}>
              <Icon className="h-6 w-6" aria-hidden />
            </span>
            <h3 className="mt-5 text-lg font-bold">{title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
          </article>
        ))}
      </div>
    </div>
  </section>
);

export default FeaturesSection;
