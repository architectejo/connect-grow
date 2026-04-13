import { Link } from "react-router-dom";

const FooterSection = () => {
  return (
    <footer className="bg-foreground py-16">
      <div className="container mx-auto px-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-sm">C+</span>
              </div>
              <span className="text-xl font-bold text-background">Connecte<span className="text-primary">+</span></span>
            </div>
            <p className="text-sm text-background/50">
              La place de marché locale qui connecte les communautés.
            </p>
          </div>

          {[
            {
              title: "Plateforme",
              links: ["Vendre", "Acheter", "Échanger", "Événements"],
            },
            {
              title: "Entreprise",
              links: ["À propos", "Contact", "Carrières", "Presse"],
            },
            {
              title: "Légal",
              links: ["CGU", "Confidentialité", "Cookies", "Mentions légales"],
            },
          ].map((col) => (
            <div key={col.title}>
              <h4 className="text-sm font-semibold text-background mb-4">{col.title}</h4>
              <ul className="space-y-2">
                {col.links.map((link) => (
                  <li key={link}>
                    <a href="#" className="text-sm text-background/50 hover:text-background transition-colors">
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 pt-8 border-t border-background/10 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-sm text-background/40">© 2026 Connecte+. Tous droits réservés.</p>
          <p className="text-sm text-background/40">Paiements sécurisés par Laxpaie</p>
        </div>
      </div>
    </footer>
  );
};

export default FooterSection;
