import type { Ref } from "react";
import { useTranslation } from "react-i18next";
import { errorProps, Field, PasswordInput } from "@/components/auth/FormFields";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { SensitiveConfirmValue } from "@/lib/team";


interface SensitiveConfirmFieldsProps {
  /** Préfixe des identifiants (unique par fenêtre). */
  idPrefix: string;
  value: SensitiveConfirmValue;
  onChange: (value: SensitiveConfirmValue) => void;
  /** Libellé de la case (« Je confirme ce changement », « Je confirme le transfert de propriété »). */
  confirmLabel: string;
  /** Erreur de ressaisie (403 reauthentication_failed), reliée au champ mot de passe. */
  error?: string;
  disabled?: boolean;
  passwordRef?: Ref<HTMLInputElement>;
}

/**
 * Case de confirmation et ressaisie du mot de passe, exigées par le serveur pour un transfert de propriété, une promotion vers
 * Propriétaire et la rétrogradation d'un Propriétaire. L'état reste dans la fenêtre qui l'utilise (mémoire du composant) :
 * le mot de passe n'est ni persisté, ni envoyé ailleurs que dans le corps de la requête.
 */
export function SensitiveConfirmFields({ idPrefix, value, onChange, confirmLabel, error, disabled, passwordRef }: SensitiveConfirmFieldsProps) {
  const { t } = useTranslation();
  const checkId = `${idPrefix}-confirm`;
  const passwordId = `${idPrefix}-password`;
  return (
    <div className="space-y-4">
      <div className="flex min-h-11 items-center gap-3">
        <Checkbox
          id={checkId}
          checked={value.confirmed}
          disabled={disabled}
          onCheckedChange={(checked) => onChange({ ...value, confirmed: checked === true })}
        />
        <Label htmlFor={checkId} className="min-h-11 flex-1 cursor-pointer py-3 text-sm leading-snug">
          {confirmLabel}
        </Label>
      </div>
      <Field label={t("team.passwordLabel")} htmlFor={passwordId} error={error} hint={t("team.passwordHelp")}>
        <PasswordInput
          id={passwordId}
          ref={passwordRef}
          name="current-password"
          autoComplete="current-password"
          value={value.password}
          disabled={disabled}
          onChange={(event) => onChange({ ...value, password: event.target.value })}
          {...errorProps(passwordId, error)}
        />
      </Field>
    </div>
  );
}
