import { Link } from "react-router-dom";
import { Logo } from "@/components/layout/Logo";

const columns = [
  {
    title: "Marketplace",
    links: [
      { label: "Toutes les annonces", to: "/marketplace" },
      { label: "Annonces échangeables", to: "/marketplace?is_exchangeable=true" },
      { label: "Entreprises", to: "/businesses" },
      { label: "Publier une annonce", to: "/create-post" },
    ],
  },
  {
    title: "Aide",
    links: [
      { label: "Comment ça marche", to: "/#comment-ca-marche" },
      { label: "Pourquoi nous faire confiance", to: "/#confiance" },
    ],
  },
];

// Documents légaux en cours de rédaction (CDC 11.3) : affichés sans lien tant qu'ils n'existent pas.
const legal = ["Conditions d'utilisation", "Confidentialité"];

const FooterSection = () => (
  <footer className="border-t bg-card">
    <div className="container py-12 md:py-16">
      <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="space-y-4">
          <Logo />
          <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
            La marketplace de confiance pour acheter, vendre et échanger près de chez vous, à Kinshasa.
          </p>
        </div>

        {columns.map((column) => (
          <nav key={column.title} aria-label={column.title}>
            <h2 className="mb-4 text-xs font-bold uppercase tracking-[0.14em] text-foreground">{column.title}</h2>
            <ul className="space-y-2.5">
              {column.links.map((link) => (
                <li key={link.label}>
                  <Link to={link.to} className="text-sm text-muted-foreground transition-colors hover:text-primary">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>

      <div className="mt-12 flex flex-col gap-3 border-t pt-6 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between">
        <p>© {new Date().getFullYear()} Connecte+. Tous droits réservés.</p>
        <p className="flex flex-wrap gap-x-4 gap-y-1">
          {legal.map((item) => (
            <span key={item}>{item}</span>
          ))}
          <span>Réalisé par IMARA TECH Group</span>
        </p>
      </div>
    </div>
  </footer>
);

export default FooterSection;
