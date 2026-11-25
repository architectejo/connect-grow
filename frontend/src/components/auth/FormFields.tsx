import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { AlertCircle, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { normalizeLocalPhone, formatLocalPhone, PHONE_PREFIX, passwordStrength } from "@/lib/validation";
import { cn } from "@/lib/utils";

interface FieldProps {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: ReactNode;
  /** Élément aligné à droite du libellé (ex. « Mot de passe oublié ? »). */
  aside?: ReactNode;
  children: ReactNode;
}

/** Libellé, champ, aide et message d'erreur relié au champ pour les lecteurs d'écran. */
export function Field({ label, htmlFor, error, hint, aside, children }: FieldProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={htmlFor} className="text-sm font-semibold">
          {label}
        </Label>
        {aside}
      </div>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} role="alert" className="flex items-center gap-1.5 text-sm font-medium text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          {error}
        </p>
      ) : (
        hint && <p className="text-xs text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}

export const fieldInputClass = "h-12 rounded-xl bg-card text-base";

export const errorProps = (id: string, error?: string) => ({
  "aria-invalid": !!error || undefined,
  "aria-describedby": error ? `${id}-error` : undefined,
});

/** Drapeau de la RDC en SVG : l'emoji 🇨🇩 s'affiche « CD » sous Windows. */
const DrcFlag = () => (
  <svg viewBox="0 0 20 15" className="h-3.5 w-5 shrink-0 overflow-hidden rounded-[2px]" aria-hidden>
    <rect width="20" height="15" fill="#007fff" />
    <path d="M0 12.6 16.8 0H20v2.4L3.2 15H0z" fill="#f7d618" />
    <path d="M0 13.8 18.4 0H20v1.2L1.6 15H0z" fill="#ce1021" />
    <path d="m3.6 1.2.62 1.9h2l-1.62 1.18.62 1.9-1.62-1.18L1.98 6.18l.62-1.9L.98 3.1h2z" fill="#f7d618" />
  </svg>
);

interface PhoneInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> {
  /** Les 9 chiffres après +243. */
  value: string;
  onChange: (digits: string) => void;
  invalid?: boolean;
}

/** Numéro congolais : préfixe +243 fixe, 9 chiffres, espaces ajoutés à l'affichage. */
export const PhoneInput = forwardRef<HTMLInputElement, PhoneInputProps>(({ value, onChange, invalid, className, ...props }, ref) => (
  <div
    className={cn(
      "flex h-12 items-center overflow-hidden rounded-xl border border-input bg-card ring-offset-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2",
      invalid && "border-destructive",
      className,
    )}
  >
    <span className="flex h-full items-center gap-1.5 border-r bg-muted px-3 text-sm font-semibold text-foreground" aria-hidden>
      <DrcFlag /> {PHONE_PREFIX}
    </span>
    <input
      ref={ref}
      type="tel"
      inputMode="numeric"
      autoComplete="tel-national"
      placeholder="81 234 5678"
      value={formatLocalPhone(value)}
      onChange={(e) => onChange(normalizeLocalPhone(e.target.value))}
      className="h-full min-w-0 flex-1 bg-transparent px-3 text-base tracking-wide outline-none placeholder:text-muted-foreground"
      {...props}
    />
  </div>
));
PhoneInput.displayName = "PhoneInput";

interface PasswordInputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Affiche la jauge de robustesse (inscription, nouveau mot de passe). */
  showStrength?: boolean;
}

const strengthColors = ["bg-muted", "bg-destructive", "bg-warning", "bg-info", "bg-success"];

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(({ showStrength, className, value, ...props }, ref) => {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const strength = passwordStrength(String(value ?? ""));
  const meterId = useId();

  return (
    <div className="space-y-2">
      <div className="relative">
        <Input
          ref={ref}
          type={visible ? "text" : "password"}
          value={value}
          className={cn(fieldInputClass, "pr-12", className)}
          aria-describedby={showStrength ? meterId : undefined}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute right-1.5 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label={visible ? t("authForm.hidePassword") : t("authForm.showPassword")}
          aria-pressed={visible}
        >
          {visible ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
        </button>
      </div>
      {showStrength && String(value ?? "").length > 0 && (
        <div id={meterId} className="flex items-center gap-3" aria-live="polite">
          <div className="flex flex-1 gap-1" aria-hidden>
            {[1, 2, 3, 4].map((level) => (
              <span
                key={level}
                className={cn("h-1.5 flex-1 rounded-full transition-colors", level <= strength ? strengthColors[strength] : "bg-muted")}
              />
            ))}
          </div>
          <span className="w-16 text-right text-xs font-medium text-muted-foreground">
            <span className="sr-only">{t("authForm.strengthPrefix")}</span>
            {strength > 0 && t(`authForm.strength.${strength}`)}
          </span>
        </div>
      )}
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";

/** Choix e-mail / téléphone en segments. */
export function MethodToggle<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; icon: React.ComponentType<{ className?: string }> }[];
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="grid grid-cols-2 gap-1 rounded-xl bg-muted p-1">
      {options.map(({ value: optionValue, label: optionLabel, icon: Icon }) => {
        const selected = value === optionValue;
        return (
          <button
            key={optionValue}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(optionValue)}
            className={cn(
              "flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all",
              selected ? "bg-card text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {optionLabel}
          </button>
        );
      })}
    </div>
  );
}

/** Message d'erreur général d'un formulaire. */
export function FormAlert({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/10 p-3.5 text-sm font-medium text-destructive">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      {message}
    </div>
  );
}
