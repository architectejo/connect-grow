import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

interface LogoProps {
  /** Afficher la signature sous le nom. */
  withTagline?: boolean;
  className?: string;
}

export function Logo({ withTagline = true, className }: LogoProps) {
  const { t } = useTranslation();
  return (
    <Link to="/" className={cn("group flex items-center gap-2.5 rounded-lg", className)} aria-label={t("brand.name")}>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-xl border bg-white p-1 shadow-soft transition-transform duration-300 group-hover:scale-105">
        <img src="/logo-mark.png" alt="" className="h-full w-full object-contain" width={28} height={28} />
      </span>
      <span className="flex flex-col">
        <span className="font-display text-lg font-extrabold leading-none tracking-tight text-foreground">
          Connecte<span className="text-primary">+</span>
        </span>
        {withTagline && (
          <span className="mt-1 hidden text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-muted-foreground sm:block">
            {t("brand.tagline")}
          </span>
        )}
      </span>
    </Link>
  );
}
