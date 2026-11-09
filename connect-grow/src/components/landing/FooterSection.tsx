import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Logo } from "@/components/layout/Logo";
import { useFeatures } from "@/hooks/use-features";

type FooterLink = { labelKey: string; to: string; exchangeOnly?: boolean };
const columns: { titleKey: string; links: FooterLink[] }[] = [
  {
    titleKey: "landing.footer.marketplace",
    links: [
      { labelKey: "landing.footer.allListings", to: "/marketplace" },
      { labelKey: "landing.footer.exchangeListings", to: "/marketplace?is_exchangeable=true", exchangeOnly: true },
      { labelKey: "landing.footer.organizations", to: "/businesses" },
      { labelKey: "landing.footer.publish", to: "/create-post" },
    ],
  },
  {
    titleKey: "landing.footer.help",
    links: [
      { labelKey: "landing.footer.howItWorks", to: "/#comment-ca-marche" },
      { labelKey: "landing.footer.whyTrust", to: "/#confiance" },
    ],
  },
];

// Documents légaux en cours de rédaction (CDC 11.3) : affichés sans lien tant qu'ils n'existent pas.
const legal = ["landing.footer.terms", "landing.footer.privacy"];

const FooterSection = () => {
  const { t } = useTranslation();
  const { exchangeEnabled } = useFeatures();
  return (
  <footer className="border-t bg-card">
    <div className="container py-12 md:py-16">
      <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="space-y-4">
          <Logo />
          <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
            {exchangeEnabled ? t("exchange.tagline") : t("exchange.taglineNoExchange")}
          </p>
        </div>

        {columns.map((column) => (
          <nav key={column.titleKey} aria-label={t(column.titleKey)}>
            <h2 className="mb-4 text-xs font-bold uppercase tracking-[0.14em] text-foreground">{t(column.titleKey)}</h2>
            <ul className="space-y-2.5">
              {column.links.filter((link) => exchangeEnabled || !link.exchangeOnly).map((link) => (
                <li key={link.labelKey}>
                  <Link to={link.to} className="text-sm text-muted-foreground transition-colors hover:text-primary">
                    {link.exchangeOnly ? t("exchange.footerLink") : t(link.labelKey)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>

      <div className="mt-12 flex flex-col gap-3 border-t pt-6 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between">
        <p>{t("landing.footer.rights", { year: new Date().getFullYear() })}</p>
        <p className="flex flex-wrap gap-x-4 gap-y-1">
          {legal.map((item) => (
            <span key={item}>{t(item)}</span>
          ))}
          <span>{t("landing.footer.madeBy")}</span>
        </p>
      </div>
    </div>
  </footer>
  );
};

export default FooterSection;
