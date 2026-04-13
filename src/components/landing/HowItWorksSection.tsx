import { UserPlus, Upload, HandCoins, TrendingUp } from "lucide-react";

const steps = [
  {
    icon: UserPlus,
    step: "01",
    title: "Créez votre compte",
    description: "Inscrivez-vous en tant que particulier ou entreprise en quelques secondes.",
  },
  {
    icon: Upload,
    step: "02",
    title: "Publiez vos offres",
    description: "Ajoutez vos produits, services ou événements avec photos et localisation.",
  },
  {
    icon: HandCoins,
    step: "03",
    title: "Vendez ou échangez",
    description: "Recevez des paiements sécurisés ou proposez des échanges directs.",
  },
  {
    icon: TrendingUp,
    step: "04",
    title: "Suivez vos résultats",
    description: "Consultez vos analytics et boostez vos publications les plus performantes.",
  },
];

const HowItWorksSection = () => {
  return (
    <section id="how-it-works" className="py-24 bg-muted/50">
      <div className="container mx-auto px-4">
        <div className="text-center max-w-xl mx-auto mb-16">
          <p className="text-sm font-medium text-primary uppercase tracking-wider mb-3">Comment ça marche</p>
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Simple et efficace
          </h2>
          <p className="text-muted-foreground">
            En 4 étapes, commencez à vendre et à développer votre activité localement.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {steps.map((step, index) => (
            <div key={step.step} className="relative text-center">
              {index < steps.length - 1 && (
                <div className="hidden md:block absolute top-10 left-[60%] w-[80%] h-px bg-border" />
              )}
              <div className="w-20 h-20 rounded-2xl gradient-primary mx-auto mb-5 flex items-center justify-center shadow-primary-glow">
                <step.icon size={32} className="text-primary-foreground" />
              </div>
              <span className="text-xs font-bold text-primary uppercase tracking-widest">Étape {step.step}</span>
              <h3 className="text-lg font-semibold text-foreground mt-2 mb-2">{step.title}</h3>
              <p className="text-sm text-muted-foreground">{step.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;
