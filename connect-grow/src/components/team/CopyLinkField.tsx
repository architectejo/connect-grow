import { useEffect, useRef, useState } from "react";
import { Check, Copy, Share2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface CopyLinkFieldProps {
  /** Lien complet. Il n'est écrit que dans le champ de saisie : jamais dans un toast, une région `aria-live`, un journal ni un attribut. */
  value: string;
  shareTitle: string;
  shareText: string;
  /** Le lien vient d'être copié ou partagé (le parent en déduit qu'il a bien été récupéré). */
  onCopied: () => void;
  /** Annonce vocale (région `aria-live` de la page) : jamais le lien. */
  onAnnounce?: (message: string) => void;
}

const COPIED_MS = 3000;

/** Copie via le presse-papiers, puis via `execCommand` sur le champ sélectionné (WebView, contexte non sécurisé). */
async function copyText(value: string, input: HTMLInputElement | null): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    /* refus ou contexte non sécurisé : repli ci-dessous */
  }
  try {
    if (!input) return false;
    input.focus();
    input.select();
    return typeof document.execCommand === "function" && document.execCommand("copy");
  } catch {
    return false;
  }
}

/** Champ en lecture seule avec « Copier le lien » et, si l'appareil sait partager, « Partager ». */
export function CopyLinkField({ value, shareTitle, shareText, onCopied, onAnnounce }: CopyLinkFieldProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const markCopied = () => {
    setCopied(true);
    setFailed(false);
    onCopied();
    onAnnounce?.(t("team.invite.copied"));
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), COPIED_MS);
  };

  const copy = async () => {
    if (await copyText(value, inputRef.current)) markCopied();
    else {
      setFailed(true);
      inputRef.current?.select();
    }
  };

  const share = async () => {
    try {
      await navigator.share({ title: shareTitle, text: shareText, url: value });
      onCopied();
    } catch (error) {
      // Annulation par l'utilisateur : pas une erreur
      if ((error as { name?: string } | null)?.name !== "AbortError") setFailed(true);
    }
  };

  return (
    <div className="space-y-3">
      <Input
        ref={inputRef}
        readOnly
        value={value}
        inputMode="none"
        autoComplete="off"
        spellCheck={false}
        aria-label={t("team.invite.linkField")}
        aria-describedby={failed ? "copy-link-failed" : undefined}
        className="h-12 truncate rounded-xl bg-card text-base"
        onFocus={(event) => event.currentTarget.select()}
      />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="button" className="min-h-12 w-full sm:flex-1" onClick={() => void copy()}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          {copied ? t("team.invite.copied") : t("team.invite.copy")}
        </Button>
        {canShare && (
          <Button type="button" variant="outline" className="min-h-12 w-full sm:w-auto" onClick={() => void share()}>
            <Share2 aria-hidden />
            {t("team.invite.share")}
          </Button>
        )}
      </div>
      {failed && (
        <p id="copy-link-failed" role="alert" className="text-sm font-medium text-destructive">
          {t("team.invite.copyFailed")}
        </p>
      )}
    </div>
  );
}
