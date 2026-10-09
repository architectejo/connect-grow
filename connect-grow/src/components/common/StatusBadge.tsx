import { cva } from "class-variance-authority";
import { BadgeCheck, Flame, Megaphone, Repeat, ShieldCheck, Sparkles, Wrench, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PostCondition } from "@/api/types";
import { cn } from "@/lib/utils";

export type StatusBadgeKind =
  | "verified"
  | "reliable"
  | "trending"
  | "sponsored"
  | "exchangeable"
  | "service"
  | PostCondition;

const badgeStyles = cva(
  "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full font-semibold leading-none",
  {
    variants: {
      tone: {
        success: "bg-success/10 text-success ring-1 ring-inset ring-success/25",
        sun: "bg-sun text-sun-foreground",
        neutral: "bg-foreground/80 text-background backdrop-blur-sm",
        primary: "bg-primary/10 text-primary ring-1 ring-inset ring-primary/20",
        muted: "bg-secondary text-secondary-foreground",
      },
      size: {
        sm: "px-2 py-1 text-[11px] [&_svg]:h-3 [&_svg]:w-3",
        md: "px-2.5 py-1.5 text-xs [&_svg]:h-3.5 [&_svg]:w-3.5",
      },
    },
    defaultVariants: { size: "sm" },
  },
);

const config: Record<StatusBadgeKind, { icon?: LucideIcon; tone: "success" | "sun" | "neutral" | "primary" | "muted" }> = {
  verified: { icon: BadgeCheck, tone: "success" },
  reliable: { icon: ShieldCheck, tone: "success" },
  trending: { icon: Flame, tone: "sun" },
  // Cahier des charges 3.8 : une annonce boostée porte toujours le libellé « Sponsorisé »
  sponsored: { icon: Megaphone, tone: "neutral" },
  exchangeable: { icon: Repeat, tone: "primary" },
  service: { icon: Wrench, tone: "primary" },
  NEUF: { icon: Sparkles, tone: "muted" },
  OCCASION: { tone: "muted" },
  RECONDITIONNE: { tone: "muted" },
};

interface StatusBadgeProps {
  kind: StatusBadgeKind;
  size?: "sm" | "md";
  /** N'afficher que l'icône (le libellé reste lu par les lecteurs d'écran). */
  iconOnly?: boolean;
  className?: string;
}

export function StatusBadge({ kind, size, iconOnly, className }: StatusBadgeProps) {
  const { t } = useTranslation();
  const { icon: Icon, tone } = config[kind];
  const label = t(`badge.${kind}`);

  return (
    <span
      className={cn(badgeStyles({ tone, size }), iconOnly && "p-0 bg-transparent ring-0", className)}
      title={iconOnly ? label : undefined}
    >
      {Icon && <Icon aria-hidden />}
      {iconOnly ? <span className="sr-only">{label}</span> : label}
    </span>
  );
}
