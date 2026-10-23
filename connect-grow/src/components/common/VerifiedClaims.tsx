import { BadgeCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { VerificationSummary, VerifiedClaim } from "@/api/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { formatMonthYear } from "@/lib/format";
import { cn } from "@/lib/utils";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Libellé d'une mention : le dictionnaire du client d'abord, le libellé du serveur en repli pour un code inconnu. */
export function claimLabel(t: Translate, claim: Pick<VerifiedClaim, "code" | "label">): string {
  const translated = t(`claims.${claim.code}`, { defaultValue: "" });
  return translated || claim.label;
}

/** Nombre de mentions montrées dans la forme compacte (cartes d'offre, annuaire). */
export const COMPACT_MAX_CLAIMS = 2;

interface VerifiedClaimsProps {
  claims?: VerifiedClaim[] | null;
  summary?: VerificationSummary | null;
  /** Forme compacte (cartes d'offre, annuaire) : deux mentions au plus puis « +N », sans ligne de synthèse. */
  compact?: boolean;
  /** Bouton « Que signifie cette mention ? » (forme complète seulement). */
  showHelp?: boolean;
  className?: string;
}

/**
 * Mentions précises de vérification (règle 3) : « RCCM vérifié », jamais « Vérifié » seul.
 * La synthèse « Organisation vérifiée » n'apparaît que si le serveur la confirme, et toujours suivie de la liste.
 * Rien n'est affiché sans mention (pas de « Non vérifié »).
 */
export function VerifiedClaims({ claims, summary, compact = false, showHelp = true, className }: VerifiedClaimsProps) {
  const { t } = useTranslation();
  const list = claims ?? [];
  if (list.length === 0) return null;

  const shown = compact ? list.slice(0, COMPACT_MAX_CLAIMS) : list;
  const hidden = list.length - shown.length;
  const complete = !compact && summary?.complete === true && !!summary.label;

  return (
    <div className={cn("space-y-1.5", className)}>
      {complete && (
        <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <BadgeCheck className="h-4 w-4 text-success" aria-hidden />
          {t("claims.summary")}
        </p>
      )}
      <ul aria-label={t("claims.listLabel")} className="flex flex-wrap items-center gap-1.5">
        {shown.map((claim) => {
          const label = claimLabel(t as Translate, claim);
          const date = !compact && claim.verified_at ? t("verif.claimDate", { date: formatMonthYear(claim.verified_at) }) : undefined;
          return (
            <li
              key={claim.code}
              title={date}
              className={cn(
                "inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-success/10 font-semibold text-success ring-1 ring-inset ring-success/25",
                compact ? "px-2 py-1 text-[11px] [&_svg]:h-3 [&_svg]:w-3" : "px-2.5 py-1.5 text-xs [&_svg]:h-3.5 [&_svg]:w-3.5",
              )}
            >
              <BadgeCheck aria-hidden />
              <span>{label}</span>
              {date && <span className="sr-only"> ({date})</span>}
            </li>
          );
        })}
        {hidden > 0 && (
          <li className="text-[11px] font-semibold text-muted-foreground" aria-label={t("claims.moreAria", { count: hidden })}>
            +{hidden}
          </li>
        )}
      </ul>
      {!compact && showHelp && (
        <Popover>
          <PopoverTrigger className="rounded text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {t("claims.helpTrigger")}
          </PopoverTrigger>
          <PopoverContent className="w-72 text-sm">
            <p className="mb-1 font-semibold">{t("claims.helpTitle")}</p>
            <p className="text-muted-foreground">{t("claims.helpBody")}</p>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
