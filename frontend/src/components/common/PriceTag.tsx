import { useTranslation } from "react-i18next";
import type { Currency } from "@/api/types";
import { formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

const sizes = {
  sm: "text-base",
  md: "text-lg",
  lg: "text-2xl md:text-3xl",
} as const;

interface PriceTagProps {
  amount: string | number;
  currency?: Currency;
  negotiable?: boolean;
  size?: keyof typeof sizes;
  className?: string;
}

/** Prix toujours affiché avec sa devise (USD ou CDF), cahier des charges 2.3. */
export function PriceTag({ amount, currency = "USD", negotiable, size = "md", className }: PriceTagProps) {
  const { t } = useTranslation();

  return (
    <div className={cn("flex flex-wrap items-baseline gap-x-2 gap-y-1", className)}>
      <span className={cn("font-display font-extrabold tracking-tight text-foreground tabular-nums", sizes[size])}>
        {formatPrice(amount, currency)}
      </span>
      {negotiable && (
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-semibold text-secondary-foreground">
          {t("price.negotiable")}
        </span>
      )}
    </div>
  );
}
