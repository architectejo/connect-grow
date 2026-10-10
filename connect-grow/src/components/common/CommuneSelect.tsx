import { MapPin } from "lucide-react";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCities } from "@/hooks/use-marketplace";
import { cn } from "@/lib/utils";

const ALL = "all";

interface CommuneSelectProps {
  /** Identifiant de commune, ou "" pour toutes. */
  value: string;
  onChange: (communeId: string) => void;
  placeholder?: string;
  className?: string;
  id?: string;
  /** Propose « toutes les communes » (filtres) ; à désactiver pour un champ obligatoire. */
  allowAll?: boolean;
  invalid?: boolean;
  /** Nom accessible quand aucun <label> n'est relié au champ. */
  "aria-label"?: string;
}

/** Choix d'une commune, regroupées par ville (Kinshasa et ses 24 communes au lancement). */
export function CommuneSelect({
  value,
  onChange,
  placeholder = "Toutes les communes",
  className,
  id,
  allowAll = true,
  invalid,
  "aria-label": ariaLabel,
}: CommuneSelectProps) {
  const { data: cities = [], isLoading } = useCities();

  return (
    <Select
      value={value || (allowAll ? ALL : "")}
      onValueChange={(v) => onChange(v === ALL ? "" : v)}
      disabled={isLoading}
    >
      <SelectTrigger id={id} className={cn("gap-2", invalid && "border-destructive", className)} aria-invalid={invalid || undefined}
        aria-label={ariaLabel}
      >
        <MapPin className="h-4 w-4 shrink-0 text-primary" aria-hidden />
        {/* La valeur occupe l'espace entre l'icône et la flèche, alignée à gauche */}
        <span className="min-w-0 flex-1 truncate text-left">
          <SelectValue placeholder={placeholder} />
        </span>
      </SelectTrigger>
      <SelectContent className="max-h-80 rounded-xl">
        {allowAll && <SelectItem value={ALL}>{placeholder}</SelectItem>}
        {cities.map((city) => (
          <SelectGroup key={city.id}>
            {cities.length > 1 && <SelectLabel>{city.name}</SelectLabel>}
            {city.communes.map((commune) => (
              <SelectItem key={commune.id} value={commune.id}>
                {commune.name}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
