import type { Ref } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/contexts/AuthContext";
import { errorProps, Field, PasswordInput } from "@/components/auth/FormFields";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { SensitiveConfirmValue } from "@/lib/team";


interface SensitiveConfirmFieldsProps {
  /** Préfixe des identifiants (unique par fenêtre). */
  idPrefix: string;
  value: SensitiveConfirmValue;
  onChange: (value: SensitiveConfirmValue) => void;
  /** Libellé de la case (« Je confirme ce changement », « Je confirme le transfert d'administration principale »). */
  confirmLabel: string;
  /** Erreur de ressaisie (403 reauthentication_failed), reliée au champ mot de passe. */
  error?: string;
  disabled?: boolean;
  passwordRef?: Ref<HTMLInputElement>;
  /** Faux si le formulaire rend déjà `LoginUsernameField` en tête (E6g). */
  withUsername?: boolean;
}

/**
 * Identifiant de connexion du compte, caché et en lecture seule, placé avant le mot de passe : les gestionnaires de mots de
 * passe associent la ressaisie au bon compte au lieu de prendre un autre champ (code, étiquette) pour un identifiant.
 */
export function LoginUsernameField() {
  const { user } = useAuth();
  const login = user?.phone || user?.email || "";
  return <input type="text" name="username" autoComplete="username" value={login} readOnly hidden />;
}

/**
 * Case de confirmation et ressaisie du mot de passe, exigées par le serveur pour un transfert d'administration principale, une promotion vers
 * Administrateur principal et la rétrogradation d'un Administrateur principal. L'état reste dans la fenêtre qui l'utilise (mémoire du composant) :
 * le mot de passe n'est ni persisté, ni envoyé ailleurs que dans le corps de la requête.
 */
export function SensitiveConfirmFields({ idPrefix, value, onChange, confirmLabel, error, disabled, passwordRef, withUsername = true }: SensitiveConfirmFieldsProps) {
  const { t } = useTranslation();
  const checkId = `${idPrefix}-confirm`;
  const passwordId = `${idPrefix}-password`;
  return (
    <div className="space-y-4">
      {withUsername && <LoginUsernameField />}
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
