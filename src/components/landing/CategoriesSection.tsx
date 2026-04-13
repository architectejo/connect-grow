import { Smartphone, Car, Home, Shirt, BookOpen, Wrench, Dumbbell, Utensils } from "lucide-react";

const categories = [
  { icon: Smartphone, label: "Électronique", count: 1240 },
  { icon: Car, label: "Véhicules", count: 856 },
  { icon: Home, label: "Immobilier", count: 432 },
  { icon: Shirt, label: "Mode", count: 2100 },
  { icon: BookOpen, label: "Éducation", count: 680 },
  { icon: Wrench, label: "Services", count: 945 },
  { icon: Dumbbell, label: "Sport", count: 520 },
  { icon: Utensils, label: "Alimentation", count: 1380 },
];

const CategoriesSection = () => {
  return (
    <section id="categories" className="py-24 bg-background">
      <div className="container mx-auto px-4">
        <div className="text-center max-w-xl mx-auto mb-16">
          <p className="text-sm font-medium text-primary uppercase tracking-wider mb-3">Catégories</p>
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Explorez par secteur
          </h2>
          <p className="text-muted-foreground">
            Des milliers d'offres organisées par catégorie pour trouver exactement ce que vous cherchez.
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {categories.map((cat) => (
            <button
              key={cat.label}
              className="group flex flex-col items-center gap-3 p-6 rounded-xl bg-card border border-border hover:border-primary/30 transition-all duration-300 shadow-card hover:shadow-lg"
            >
              <div className="w-14 h-14 rounded-xl bg-muted group-hover:gradient-primary flex items-center justify-center transition-all">
                <cat.icon size={24} className="text-muted-foreground group-hover:text-primary-foreground transition-colors" />
              </div>
              <span className="text-sm font-medium text-foreground">{cat.label}</span>
              <span className="text-xs text-muted-foreground">{cat.count.toLocaleString()} annonces</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
};

export default CategoriesSection;
