import { useEffect, useState } from "react";
import type { PostFilters } from "@/api/types";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { FilterKey } from "./use-post-filters";

interface FiltersPanelProps {
  filters: PostFilters;
  onChange: (patch: Partial<Record<FilterKey, string | undefined>>) => void;
  className?: string;
}

const conditions = [
  { value: "", label: "Tous" },
  { value: "NEUF", label: "Neuf" },
  { value: "OCCASION", label: "Occasion" },
  { value: "RECONDITIONNE", label: "Reconditionné" },
];

const currencies = [
  { value: "", label: "Toutes" },
  { value: "USD", label: "USD ($)" },
  { value: "CDF", label: "CDF (FC)" },
];

/** Groupe de boutons à choix unique (état, devise). */
function ChoiceGroup({
  label,
  options,
  value,
  onSelect,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onSelect: (value: string) => void;
}) {
  return (
    <fieldset className="space-y-2.5">
      <legend className="text-sm font-semibold text-foreground">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const selected = value === option.value;
          return (
            <button
              key={option.value || "all"}
              type="button"
              aria-pressed={selected}
              onClick={() => onSelect(option.value)}
              className={cn(
                "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
                selected
                  ? "border-primary bg-primary text-primary-foreground"
                  : "bg-card text-foreground hover:border-primary/40 hover:bg-primary/5",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Filtres de recherche (CDC 3.2). Chaque changement met à jour l'URL, donc les résultats. */
export function FiltersPanel({ filters, onChange, className }: FiltersPanelProps) {
  // Les prix sont appliqués à la validation (Entrée ou sortie du champ), pas à chaque frappe
  const [priceMin, setPriceMin] = useState(filters.price_min ?? "");
  const [priceMax, setPriceMax] = useState(filters.price_max ?? "");

  useEffect(() => setPriceMin(filters.price_min ?? ""), [filters.price_min]);
  useEffect(() => setPriceMax(filters.price_max ?? ""), [filters.price_max]);

  const applyPrices = () => onChange({ price_min: priceMin || undefined, price_max: priceMax || undefined });
  const onPriceKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      applyPrices();
    }
  };

  return (
    <div className={cn("space-y-7", className)}>
      <div className="space-y-2.5">
        <Label htmlFor="filter-commune" className="text-sm font-semibold">
          Commune
        </Label>
        <CommuneSelect
          id="filter-commune"
          value={filters.commune ?? ""}
          onChange={(commune) => onChange({ commune })}
          className="h-11 rounded-xl"
        />
      </div>

      <fieldset className="space-y-2.5">
        <legend className="text-sm font-semibold text-foreground">Prix</legend>
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            placeholder="Min"
            aria-label="Prix minimum"
            value={priceMin}
            onChange={(e) => setPriceMin(e.target.value)}
            onBlur={applyPrices}
            onKeyDown={onPriceKey}
            className="h-11 rounded-xl"
          />
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            placeholder="Max"
            aria-label="Prix maximum"
            value={priceMax}
            onChange={(e) => setPriceMax(e.target.value)}
            onBlur={applyPrices}
            onKeyDown={onPriceKey}
            className="h-11 rounded-xl"
          />
        </div>
      </fieldset>

      <ChoiceGroup
        label="Devise"
        options={currencies}
        value={filters.currency ?? ""}
        onSelect={(currency) => onChange({ currency })}
      />

      <ChoiceGroup
        label="État"
        options={conditions}
        value={filters.condition ?? ""}
        onSelect={(condition) => onChange({ condition })}
      />

      <div className="flex items-center justify-between gap-4 rounded-xl border bg-card p-3.5">
        <Label htmlFor="filter-exchangeable" className="cursor-pointer">
          <span className="block text-sm font-semibold">Échangeable uniquement</span>
          <span className="block text-xs font-normal text-muted-foreground">Annonces ouvertes au troc</span>
        </Label>
        <Switch
          id="filter-exchangeable"
          checked={filters.is_exchangeable === "true"}
          onCheckedChange={(checked) => onChange({ is_exchangeable: checked ? "true" : undefined })}
        />
      </div>
    </div>
  );
}
