import { ShoppingBag, Repeat, Heart, BarChart3, MapPin, Star, Calendar, Megaphone } from "lucide-react";

const features = [
  {
    icon: ShoppingBag,
    title: "Vente directe",
    description: "Vendez vos produits et services avec paiement sécurisé via Laxpaie.",
  },
  {
    icon: Repeat,
    title: "Échange & Troc",
    description: "Proposez des échanges de biens entre particuliers de votre ville.",
  },
  {
    icon: Heart,
    title: "Collecte de fonds",
    description: "Les ONG lancent des campagnes de financement participatif transparentes.",
  },
  {
    icon: BarChart3,
    title: "Analytics avancés",
    description: "Suivez vos vues, conversions et l'impact de vos promotions en temps réel.",
  },
  {
    icon: MapPin,
    title: "Géo-recommandation",
    description: "Découvrez les offres proches de vous grâce à l'algorithme de proximité.",
  },
  {
    icon: Star,
    title: "Système de notation",
    description: "Évaluez et consultez la réputation des vendeurs avant d'acheter.",
  },
  {
    icon: Calendar,
    title: "Événements locaux",
    description: "Découvrez et publiez des événements avec billetterie intégrée.",
  },
  {
    icon: Megaphone,
    title: "Boost de visibilité",
    description: "Mettez en avant vos publications pour toucher plus de clients.",
  },
];

const FeaturesSection = () => {
  return (
    <section id="features" className="py-24 bg-background">
      <div className="container mx-auto px-4">
        <div className="text-center max-w-xl mx-auto mb-16">
          <p className="text-sm font-medium text-primary uppercase tracking-wider mb-3">Fonctionnalités</p>
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Tout ce dont vous avez besoin
          </h2>
          <p className="text-muted-foreground">
            Une plateforme complète qui connecte vendeurs, acheteurs et associations dans votre communauté.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, index) => (
            <div
              key={feature.title}
              className="group p-6 rounded-xl bg-card border border-border hover:border-primary/30 transition-all duration-300 shadow-card hover:shadow-lg"
              style={{ animationDelay: `${index * 80}ms` }}
            >
              <div className="w-12 h-12 rounded-xl gradient-primary flex items-center justify-center mb-4 group-hover:shadow-primary-glow transition-shadow">
                <feature.icon size={22} className="text-primary-foreground" />
              </div>
              <h3 className="text-base font-semibold text-foreground mb-2">{feature.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
