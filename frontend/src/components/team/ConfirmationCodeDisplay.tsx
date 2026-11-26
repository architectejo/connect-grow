import { forwardRef } from "react";
import { useTranslation } from "react-i18next";
import { formatCodeGroups, spellDigits } from "@/lib/confirmation-code";

interface ConfirmationCodeDisplayProps {
  /** Code de rattachement (6 chiffres). Ne vit que dans l'état du composant parent. */
  code: string;
  headingId: string;
  /** Titre du bloc (par défaut « Votre code de confirmation »). */
  title?: string;
}

/**
 * Bloc du code de rattachement (spec D2 §9.4 point 3, §11.3). Affiché en grand, en deux groupes (« 482 913 ») masqués aux
 * lecteurs d'écran, doublés d'une version chiffre par chiffre (« 4 8 2 9 1 3 »). Aucun bouton Copier ni Partager : le code se
 * dicte de vive voix. Jamais dans une région vivante, un `title`, un `aria-label` ni un attribut `data-*`.
 * Le titre reçoit le focus (ref, `tabIndex={-1}`) quand le code apparaît.
 */
export const ConfirmationCodeDisplay = forwardRef<HTMLHeadingElement, ConfirmationCodeDisplayProps>(function ConfirmationCodeDisplay({ code, headingId, title }, ref) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby={headingId} className="rounded-2xl border-2 border-primary/40 bg-card p-4 text-center">
      <h2 id={headingId} ref={ref} tabIndex={-1} className="text-base font-bold outline-none">
        {title ?? t("invitation.awaiting.codeTitle")}
      </h2>
      <p className="my-3 select-none font-mono text-4xl font-bold tracking-[0.3em] text-foreground">
        <span aria-hidden="true">{formatCodeGroups(code)}</span>
        <span className="sr-only">{spellDigits(code)}</span>
      </p>
      <p className="text-sm">{t("invitation.awaiting.codeInstruction")}</p>
      <p className="mt-2 text-xs text-muted-foreground">{t("invitation.awaiting.codeOnce")}</p>
    </section>
  );
});
