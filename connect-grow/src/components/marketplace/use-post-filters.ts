import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { PostFilters } from "@/api/types";
import { useFeatures } from "@/hooks/use-features";

export const FILTER_KEYS = [
  "search",
  "category",
  "city",
  "commune",
  "currency",
  "condition",
  "is_exchangeable",
  "price_min",
  "price_max",
  "ordering",
  "seller",
] as const satisfies readonly (keyof PostFilters)[];

export type FilterKey = (typeof FILTER_KEYS)[number];

/** Filtres qui réduisent les résultats (le tri et la recherche texte sont affichés à part). */
export const REFINING_KEYS: FilterKey[] = ["category", "commune", "currency", "condition", "is_exchangeable", "price_min", "price_max"];

export const DEFAULT_ORDERING = "-visibility_score";

/** Filtres de la marketplace lus et écrits dans l'URL (partageables, conservés au retour arrière). */
export function usePostFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { exchangeEnabled } = useFeatures();

  const filters = useMemo(() => {
    const result: PostFilters = {};
    for (const key of FILTER_KEYS) {
      const value = searchParams.get(key);
      // Troc éteint : le paramètre de l'URL est ignoré (jamais envoyé au serveur, jamais compté).
      if (key === "is_exchangeable" && !exchangeEnabled) continue;
      if (value) (result as Record<string, string>)[key] = value;
    }
    return result;
  }, [searchParams, exchangeEnabled]);

  const setFilters = useCallback(
    (patch: Partial<Record<FilterKey, string | undefined>>) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(patch)) {
            if (value) next.set(key, value);
            else next.delete(key);
          }
          if (next.get("ordering") === DEFAULT_ORDERING) next.delete("ordering");
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const resetFilters = useCallback(() => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams();
        const ordering = current.get("ordering");
        if (ordering) next.set("ordering", ordering);
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  const activeCount = REFINING_KEYS.filter((key) => !!filters[key]).length;

  return { filters, setFilters, resetFilters, activeCount };
}
