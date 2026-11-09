import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PostFilters } from "@/api/types";
import { useFeatures } from "@/hooks/use-features";
import { useCategories, useCities } from "@/hooks/use-marketplace";
import type { FilterKey } from "./use-post-filters";

interface ActiveFiltersProps {
  filters: PostFilters;
  onChange: (patch: Partial<Record<FilterKey, string | undefined>>) => void;
  onReset: () => void;
}

/** Filtres appliqués, retirables un par un. */
export function ActiveFilters({ filters, onChange, onReset }: ActiveFiltersProps) {
  const { t } = useTranslation();
  const { exchangeEnabled } = useFeatures();
  const { data: categories = [] } = useCategories();
  const { data: cities = [] } = useCities();

  const chips: { key: string; label: string; clear: Partial<Record<FilterKey, undefined>> }[] = [];

  if (filters.search) chips.push({ key: "search", label: `« ${filters.search} »`, clear: { search: undefined } });
  if (filters.category) {
    const name = categories.find((c) => c.id === filters.category)?.name ?? t("marketplace.active.category");
    chips.push({ key: "category", label: name, clear: { category: undefined } });
  }
  if (filters.commune) {
    const name = cities.flatMap((city) => city.communes).find((c) => c.id === filters.commune)?.name ?? t("marketplace.active.commune");
    chips.push({ key: "commune", label: name, clear: { commune: undefined } });
  }
  if (filters.price_min || filters.price_max) {
    const label =
      filters.price_min && filters.price_max
        ? `${filters.price_min} – ${filters.price_max}`
        : filters.price_min
          ? t("marketplace.active.from", { value: filters.price_min })
          : t("marketplace.active.upTo", { value: filters.price_max });
    chips.push({ key: "price", label, clear: { price_min: undefined, price_max: undefined } });
  }
  if (filters.currency) chips.push({ key: "currency", label: filters.currency, clear: { currency: undefined } });
  if (filters.condition)
    chips.push({ key: "condition", label: t(`badge.${filters.condition}`, { defaultValue: filters.condition }), clear: { condition: undefined } });
  if (exchangeEnabled && filters.is_exchangeable === "true")
    chips.push({ key: "exchange", label: t("exchange.chip"), clear: { is_exchangeable: undefined } });

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          onClick={() => onChange(chip.clear)}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 py-1.5 pl-3 pr-2 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
          aria-label={t("marketplace.active.remove", { label: chip.label })}
        >
          {chip.label}
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      ))}
      {chips.length > 1 && (
        <button type="button" onClick={onReset} className="px-2 text-sm font-semibold text-muted-foreground hover:text-foreground">
          {t("marketplace.active.clearAll")}
        </button>
      )}
    </div>
  );
}
