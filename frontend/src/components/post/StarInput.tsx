import { useId } from "react";
import { Star } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

interface StarInputProps {
  label: string;
  /** 0 = pas encore choisi. */
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}

/** Choix d'une note de 1 à 5 (groupe de boutons radio nommé, utilisable au clavier). */
export function StarInput({ label, value, onChange, disabled }: StarInputProps) {
  const { t } = useTranslation();
  const labelId = useId();
  return (
    <div className="space-y-1">
      <p id={labelId} className="text-sm font-semibold">
        {label}
      </p>
      <div role="radiogroup" aria-labelledby={labelId} className="flex items-center gap-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            role="radio"
            disabled={disabled}
            aria-checked={star === value}
            aria-label={t("reviews.starLabel", { count: star, text: t(`reviews.starTexts.${star}`) })}
            onClick={() => onChange(star)}
            className="rounded-md p-0.5 transition-transform hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Star className={cn("h-7 w-7", star <= value ? "fill-sun text-sun" : "text-muted-foreground/40")} aria-hidden />
          </button>
        ))}
        {value > 0 && <span className="ml-2 text-sm font-medium text-muted-foreground">{t(`reviews.starTexts.${value}`)}</span>}
      </div>
    </div>
  );
}
