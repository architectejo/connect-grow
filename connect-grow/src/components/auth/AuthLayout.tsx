import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, BadgeCheck, ShieldCheck, Star } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { ModeToggle } from "@/components/mode-toggle";

const reasons = [
  { icon: Star, textKey: "authLayout.reasonRated" },
  { icon: BadgeCheck, textKey: "authLayout.reasonVerified" },
  { icon: ShieldCheck, textKey: "authLayout.reasonPhone" },
] as const;

interface AuthLayoutProps {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  /** Lien secondaire sous le formulaire (« Pas encore de compte ? … »). */
  footer?: ReactNode;
}

/** Gabarit des écrans d'authentification : visuel de marque à gauche (desktop), formulaire à droite. */
export function AuthLayout({ title, description, children, footer }: AuthLayoutProps) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen bg-background">
      <aside className="relative hidden w-[44%] max-w-xl flex-col justify-between overflow-hidden gradient-hero p-10 text-white lg:flex xl:p-14">
        <div className="pointer-events-none absolute inset-0" aria-hidden>
          <div className="absolute -left-24 top-1/3 h-80 w-80 rounded-full bg-primary/40 blur-3xl" />
          <div className="absolute -right-16 bottom-10 h-64 w-64 rounded-full bg-sun/20 blur-3xl" />
        </div>

        <Link to="/" className="relative flex w-fit items-center gap-2.5">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white p-1.5">
            <img src="/logo-mark.png" alt="" className="h-full w-full object-contain" />
          </span>
          <span className="font-display text-xl font-extrabold">
            Connecte<span className="text-sun">+</span>
          </span>
        </Link>

        <div className="relative">
          <h2 className="text-balance font-display text-4xl font-extrabold leading-tight xl:text-5xl">
            {t("authLayout.headlineStart")} <span className="text-sun">{t("authLayout.headlineEmphasis")}</span>.
          </h2>
          <ul className="mt-8 space-y-4">
            {reasons.map(({ icon: Icon, textKey }) => (
              <li key={textKey} className="flex items-center gap-3 text-white/85">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10">
                  <Icon className="h-4 w-4 text-sun" aria-hidden />
                </span>
                {t(textKey)}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-sm text-white/50">{t("brand.location")}</p>
      </aside>

      <main id="contenu" className="flex flex-1 flex-col">
        <div className="flex items-center justify-between p-4 sm:p-6">
          <Link
            to="/"
            className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden /> {t("nav.home")}
          </Link>
          <ModeToggle />
        </div>

        <div className="flex flex-1 items-start justify-center px-4 pb-10 sm:items-center sm:px-6">
          <div className="w-full max-w-md">
            <div className="mb-8 lg:hidden">
              <Logo />
            </div>
            <h1 className="text-balance text-3xl font-extrabold">{title}</h1>
            {description && <p className="mt-2 text-muted-foreground">{description}</p>}
            <div className="mt-8">{children}</div>
            {footer && <div className="mt-8 text-center text-sm text-muted-foreground">{footer}</div>}
          </div>
        </div>
      </main>
    </div>
  );
}
