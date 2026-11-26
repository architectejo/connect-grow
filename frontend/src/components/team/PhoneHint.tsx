import { useTranslation } from "react-i18next";
import { spellDigits } from "@/lib/confirmation-code";
import { cn } from "@/lib/utils";

/**
 * Indice de téléphone d'une personne qui a accepté une invitation Administrateur (« ••47 », tel que reçu du serveur).
 * Texte visible pour les voyants ; version chiffre par chiffre pour les lecteurs d'écran (les puces ne sont pas lues).
 * Point unique d'affichage : l'indice n'est jamais copié dans un toast, une région vivante, un titre ni un attribut `data-*`.
 */
export function PhoneHint({ hint, className }: { hint: string; className?: string }) {
  const { t } = useTranslation();
  return (
    <span className={cn("inline", className)}>
      <span aria-hidden="true">{t("team.awaiting.phoneHint", { hint })}</span>
      <span className="sr-only">{t("team.awaiting.phoneHintAria", { digits: spellDigits(hint) })}</span>
    </span>
  );
}
