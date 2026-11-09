import { useEffect, useState } from "react";
import { REGEXP_ONLY_DIGITS } from "input-otp";
import { Trans, useTranslation } from "react-i18next";
import { Loader2, MessageSquareText, RotateCcw } from "lucide-react";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Button } from "@/components/ui/button";
import { formatLocalPhone, PHONE_PREFIX } from "@/lib/validation";
import { FormAlert } from "./FormFields";

// CDC 3.1 : code à 6 chiffres, valable 10 minutes, 3 tentatives
export const OTP_LENGTH = 6;
const VALIDITY_SECONDS = 10 * 60;
const RESEND_COOLDOWN_SECONDS = 60;

function useCountdown(seconds: number, resetKey: number) {
  const [remaining, setRemaining] = useState(seconds);
  useEffect(() => {
    setRemaining(seconds);
    const timer = window.setInterval(() => setRemaining((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [seconds, resetKey]);
  return remaining;
}

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

interface OtpStepProps {
  /** Les 9 chiffres après +243. */
  phone: string;
  code: string;
  onCodeChange: (code: string) => void;
  /** Validation du code : appelée automatiquement quand les 6 chiffres sont saisis. */
  onSubmit: () => void;
  /** Renvoie un code ; doit rejeter en cas d'échec. */
  onResend: () => Promise<unknown>;
  onChangeNumber: () => void;
  isSubmitting: boolean;
  error?: string;
  submitLabel?: string;
  /** Champs supplémentaires sous le code (ex. nouveau mot de passe). */
  children?: React.ReactNode;
  /** Désactive l'envoi automatique quand des champs restent à remplir. */
  autoSubmit?: boolean;
}

export function OtpStep({
  phone,
  code,
  onCodeChange,
  onSubmit,
  onResend,
  onChangeNumber,
  isSubmitting,
  error,
  submitLabel,
  children,
  autoSubmit = true,
}: OtpStepProps) {
  const { t } = useTranslation();
  const [sentAt, setSentAt] = useState(0);
  const [resending, setResending] = useState(false);
  const validity = useCountdown(VALIDITY_SECONDS, sentAt);
  const cooldown = useCountdown(RESEND_COOLDOWN_SECONDS, sentAt);
  const expired = validity === 0;

  const resend = async () => {
    setResending(true);
    try {
      await onResend();
      onCodeChange("");
      setSentAt((n) => n + 1);
    } catch {
      // Échec affiché par le parent ; le compte à rebours ne repart pas puisque aucun SMS n'est parti
    } finally {
      setResending(false);
    }
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="space-y-6"
    >
      <div className="flex items-start gap-3 rounded-xl bg-primary/5 p-4">
        <MessageSquareText className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
        <p className="text-sm text-foreground">
          {t("otp.sentBefore")}{" "}
          <span className="whitespace-nowrap font-semibold">
            {PHONE_PREFIX} {formatLocalPhone(phone)}
          </span>
          {" "}
          <button type="button" onClick={onChangeNumber} className="font-semibold text-primary hover:underline">
            {t("otp.change")}
          </button>
        </p>
      </div>

      <div className="space-y-3">
        <InputOTP
          maxLength={OTP_LENGTH}
          pattern={REGEXP_ONLY_DIGITS}
          value={code}
          onChange={onCodeChange}
          onComplete={() => autoSubmit && !isSubmitting && onSubmit()}
          autoFocus
          autoComplete="one-time-code"
          inputMode="numeric"
          disabled={isSubmitting || expired}
          aria-label={t("otp.label")}
          containerClassName="justify-center"
        >
          <InputOTPGroup className="gap-2">
            {Array.from({ length: OTP_LENGTH }, (_, i) => (
              <InputOTPSlot
                key={i}
                index={i}
                className="h-14 w-12 rounded-xl border bg-card font-display text-xl font-bold first:rounded-xl first:border-l last:rounded-xl sm:w-14"
              />
            ))}
          </InputOTPGroup>
        </InputOTP>
        <p className="text-center text-sm text-muted-foreground" aria-live="polite">
          {expired ? (
            <span className="font-medium text-destructive">{t("otp.expired")}</span>
          ) : (
            <Trans
              i18nKey="otp.validFor"
              values={{ time: mmss(validity) }}
              components={{ b: <span className="font-semibold tabular-nums text-foreground" /> }}
            />
          )}
        </p>
      </div>

      {children}

      <FormAlert message={error} />

      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting || expired || code.length < OTP_LENGTH}>
        {isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
        {submitLabel ?? t("otp.verify")}
      </Button>

      <div className="text-center">
        <Button type="button" variant="ghost" onClick={resend} disabled={cooldown > 0 || resending}>
          {resending ? <Loader2 className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />}
          {cooldown > 0 ? t("otp.resendIn", { seconds: cooldown }) : t("otp.resend")}
        </Button>
      </div>
    </form>
  );
}
