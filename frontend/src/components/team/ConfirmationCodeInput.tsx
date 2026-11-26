import { forwardRef } from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CONFIRMATION_CODE_LENGTH, normalizeCode } from "@/lib/confirmation-code";

interface ConfirmationCodeInputProps {
  id: string;
  /** Chiffres seulement (déjà normalisés). */
  value: string;
  onChange: (digits: string) => void;
  error?: string;
  disabled?: boolean;
}

/**
 * Champ du code de rattachement (E6g, spec D2 §8.3 point 5). Un seul champ (pas six cases) ; saisie et collage normalisés en
 * chiffres (« 482 913 » → « 482913 ») ; `autoComplete="off"` (et non `one-time-code` : le téléphone du confirmateur proposerait
 * ses propres codes SMS). Aide et erreur reliées par `aria-describedby`.
 */
export const ConfirmationCodeInput = forwardRef<HTMLInputElement, ConfirmationCodeInputProps>(function ConfirmationCodeInput(
  { id, value, onChange, error, disabled },
  ref,
) {
  const { t } = useTranslation();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  return (
    <div className="space-y-2">
      <Label htmlFor={id} className="text-sm font-semibold">
        {t("team.confirmInvite.codeLabel")}
      </Label>
      <Input
        ref={ref}
        id={id}
        name="invitation-confirmation-code"
        value={value}
        inputMode="numeric"
        autoComplete="off"
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="off"
        // 6 chiffres et une espace éventuelle à la frappe ; la valeur gardée n'a que des chiffres
        maxLength={CONFIRMATION_CODE_LENGTH + 1}
        disabled={disabled}
        className="h-12 min-h-11 w-full rounded-xl bg-card font-mono text-lg tracking-widest sm:w-40"
        aria-invalid={!!error || undefined}
        aria-describedby={error ? `${errorId} ${helpId}` : helpId}
        onChange={(event) => onChange(normalizeCode(event.target.value))}
      />
      <p id={helpId} className="text-xs text-muted-foreground">
        {t("team.confirmInvite.codeHelp")}
      </p>
      {error && (
        <p id={errorId} role="alert" className="flex items-center gap-1.5 text-sm font-medium text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
});
