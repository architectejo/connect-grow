import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { useCategories } from "@/hooks/use-marketplace";
import type { Uuid } from "@/api/types";
import { cn } from "@/lib/utils";

interface CategoryPickerProps {
  value: Uuid[];
  onChange: (ids: Uuid[]) => void;
  /** Plafond lu sur `organizations/limits/` (réglable en back-office) ; jamais codé en dur. */
  max: number;
  /** Identifiant de l'élément qui porte le libellé du groupe. */
  labelledBy: string;
  disabled?: boolean;
}

/** Sélection multiple de catégories (puces à cocher), plafonnée. Les valeurs sont des UUID de `marketplace/categories/`. */
export function CategoryPicker({ value, onChange, max, labelledBy, disabled }: CategoryPickerProps) {
  const { t } = useTranslation();
  const { data: categories = [], isLoading, isError } = useCategories();

  if (isLoading) return <Skeleton className="h-10 w-full rounded-xl" />;
  if (isError) return <p className="text-sm text-muted-foreground">{t("categories.loadError")}</p>;
  if (categories.length === 0) return <p className="text-sm text-muted-foreground">{t("categories.none")}</p>;

  const atMax = value.length >= max;
  const toggle = (id: Uuid) => onChange(value.includes(id) ? value.filter((v) => v !== id) : atMax ? value : [...value, id]);

  return (
    <div>
      <div role="group" aria-labelledby={labelledBy} className="flex flex-wrap gap-2">
        {categories.map((category) => {
          const selected = value.includes(category.id);
          return (
            <button
              key={category.id}
              type="button"
              aria-pressed={selected}
              disabled={disabled || (!selected && atMax)}
              onClick={() => toggle(category.id)}
              className={cn(
                "min-h-9 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
                selected ? "border-primary bg-primary/10 text-foreground" : "bg-card text-muted-foreground hover:border-primary/40",
              )}
            >
              {selected && <span aria-hidden>✓ </span>}
              {category.name}
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground" aria-live="polite">
        {t("categories.selected", { count: value.length })} · {t("categories.max", { count: max })}
      </p>
    </div>
  );
}
