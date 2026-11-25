import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { REGEXP_ONLY_DIGITS } from "input-otp";
import { BadgeCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { ContactChannel, ContactSettings } from "@/api/types";
import { AccessDenied, ErrorState } from "@/components/common";
import { Field, FormAlert, PhoneInput } from "@/components/auth/FormFields";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useContactSettings, useSetContactChannel, useSetContactPhone, useVerifyContactPhone } from "@/hooks/use-contact-settings";
import {
  availableChannels,
  CONSENT_CHANNELS,
  CONSENT_TEXT_VERSION,
  contactSettingsErrorMessage,
  isChannelNotAvailable,
} from "@/lib/contact-settings";
import { httpStatus } from "@/lib/errors";
import { localPhoneSchema, toE164 } from "@/lib/validation";

const OTP_LENGTH = 6;
const CHANNELS: ContactChannel[] = ["MESSAGE", "CALL", "WHATSAPP"];
const needsConsent = (channel: ContactChannel) => (CONSENT_CHANNELS as readonly string[]).includes(channel);

// --- Dialogue de consentement (texte versionné, ADR 0005 C4) ---

function ConsentDialog({
  channel,
  masked,
  pending,
  error,
  onAccept,
  onClose,
}: {
  channel: ContactChannel | null;
  masked: string;
  pending: boolean;
  error?: string;
  onAccept: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const base = `contactSettings.consent.${CONSENT_TEXT_VERSION}`;
  return (
    <Dialog open={channel !== null} onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("contactSettings.consent.title")}</DialogTitle>
          <DialogDescription>{channel ? t(`contactSettings.channels.${channel}`) : ""}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm text-foreground" data-text-version={CONSENT_TEXT_VERSION}>
          <p className="text-xs text-muted-foreground">{t(`${base}.intro`)}</p>
          <p className="font-medium">{t(`${base}.number`, { masked })}</p>
          <p>{t(`${base}.who`)}</p>
          <p>{t(`${base}.withdraw`)}</p>
          {channel === "WHATSAPP" && <p>{t(`${base}.whatsapp`)}</p>}
        </div>
        <FormAlert message={error} />
        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            {t("contactSettings.consent.cancel")}
          </Button>
          <Button type="button" onClick={onAccept} disabled={pending}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("contactSettings.consent.accept")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Numéro de contact ---

function PhoneBlock({ settings, allowLoginPhone = true }: { settings: ContactSettings; allowLoginPhone?: boolean }) {
  const inOrganization = !allowLoginPhone;
  const { t } = useTranslation();
  const setPhone = useSetContactPhone();
  const verify = useVerifyContactPhone();
  const [editing, setEditing] = useState(false);
  const [local, setLocal] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const phone = settings.phone;
  // Le serveur fournit le masque du numéro de connexion à la racine (ADR 0005 §5.1) ; null pour une organisation.
  const login = { masked: settings.login_phone_masked ?? "", available: settings.can_use_login_phone };
  const awaitingCode = !!phone && !phone.is_verified && !editing;
  const choosing = !phone || editing;

  const save = async (input: { use_login_phone: true } | { phone: string }) => {
    setError(undefined);
    try {
      const next = await setPhone.mutateAsync(input);
      setEditing(false);
      setLocal("");
      setCode("");
      toast.success(t(next.phone?.is_verified ? "contactSettings.phone.verifiedToast" : "contactSettings.phone.saved"));
    } catch (err) {
      setError(contactSettingsErrorMessage(err, { inOrganization }));
    }
  };

  const submitOther = () => {
    const valid = localPhoneSchema.safeParse(local);
    if (!valid.success) {
      setError(t("contactSettings.errors.phone_invalid"));
      return;
    }
    void save({ phone: toE164(local) });
  };

  const submitCode = async () => {
    setError(undefined);
    try {
      await verify.mutateAsync(code);
      setCode("");
      toast.success(t("contactSettings.phone.verifiedToast"));
    } catch (err) {
      setCode("");
      setError(contactSettingsErrorMessage(err, { inOrganization }));
    }
  };

  return (
    <section aria-labelledby="contact-phone-title" className="space-y-3 rounded-xl border p-4">
      <h3 id="contact-phone-title" className="font-semibold">
        {t("contactSettings.phone.title")}
      </h3>

      {phone && (
        <div>
          <p className="font-semibold tabular-nums" data-testid="contact-phone-masked">
            {phone.masked}
          </p>
          {phone.is_verified ? (
            <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-success">
              <BadgeCheck className="h-3.5 w-3.5" aria-hidden /> {t("contactSettings.phone.verified")}
            </p>
          ) : (
            <p className="mt-0.5 text-xs font-medium text-warning-foreground">{t("contactSettings.phone.unverified")}</p>
          )}
        </div>
      )}
      {!phone && <p className="text-sm text-muted-foreground">{t("contactSettings.phone.none")}</p>}

      {awaitingCode && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (code.length === OTP_LENGTH) void submitCode();
          }}
          className="space-y-3"
        >
          <Field label={t("contactSettings.phone.codeLabel")} htmlFor="contact-otp">
            <InputOTP
              id="contact-otp"
              maxLength={OTP_LENGTH}
              pattern={REGEXP_ONLY_DIGITS}
              value={code}
              onChange={(value) => {
                setCode(value);
                setError(undefined);
              }}
              inputMode="numeric"
              autoComplete="one-time-code"
              disabled={verify.isPending}
              aria-label={t("contactSettings.phone.codeLabel")}
            >
              <InputOTPGroup className="gap-2">
                {Array.from({ length: OTP_LENGTH }, (_, i) => (
                  <InputOTPSlot key={i} index={i} className="h-12 w-10 rounded-xl border bg-card first:rounded-xl first:border-l last:rounded-xl" />
                ))}
              </InputOTPGroup>
            </InputOTP>
          </Field>
          <Button type="submit" disabled={verify.isPending || code.length < OTP_LENGTH}>
            {verify.isPending && <Loader2 className="animate-spin" aria-hidden />}
            {t("contactSettings.phone.verify")}
          </Button>
        </form>
      )}

      {choosing && (
        <div className="space-y-3">
          {editing && <p className="text-xs text-muted-foreground">{t("contactSettings.phone.changeWarning")}</p>}
          {/* Le numéro personnel d'un membre n'est jamais proposé comme numéro de l'organisation */}
          {allowLoginPhone && (
            <div className="space-y-1">
              <Button
                type="button"
                variant="outline"
                disabled={!login.available || setPhone.isPending}
                onClick={() => void save({ use_login_phone: true })}
              >
                {t("contactSettings.phone.useLogin", { masked: login.masked })}
              </Button>
              <p className="text-xs text-muted-foreground">
                {login.available ? t("contactSettings.phone.useLoginHint") : t("contactSettings.phone.loginUnverified")}
              </p>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submitOther();
            }}
            className="space-y-2"
          >
            <Field label={t("contactSettings.phone.inputLabel")} htmlFor="contact-phone-input">
              <PhoneInput
                id="contact-phone-input"
                value={local}
                onChange={(digits) => {
                  setLocal(digits);
                  setError(undefined);
                }}
                invalid={!!error}
              />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={setPhone.isPending}>
                {setPhone.isPending && <Loader2 className="animate-spin" aria-hidden />}
                {t("contactSettings.phone.save")}
              </Button>
              {editing && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setEditing(false);
                    setError(undefined);
                  }}
                >
                  {t("contactSettings.phone.cancel")}
                </Button>
              )}
            </div>
          </form>
        </div>
      )}

      {phone && !editing && (
        <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)}>
          {t("contactSettings.phone.change")}
        </Button>
      )}

      <FormAlert message={error} />
    </section>
  );
}

// --- Section complète ---

export function ContactSettingsSection() {
  const { t } = useTranslation();
  const { active } = useActiveContext();
  const isOrganization = active.type === "ORGANIZATION";
  // Réglages d'une organisation : `contact.manage_channels` (administrateurs principaux, administrateurs). Le serveur reste le juge.
  const denied = isOrganization && active.confirmed && !active.capabilities.includes("contact.manage_channels");
  const query = useContactSettings(!denied);
  const setChannel = useSetContactChannel();
  const [pendingChannel, setPendingChannel] = useState<ContactChannel | null>(null);
  const [consentError, setConsentError] = useState<string>();
  const [switchError, setSwitchError] = useState<string>();

  const settings = query.data;
  const verified = !!settings?.phone?.is_verified;

  // Si le numéro est retiré ou modifié pendant que le dialogue est ouvert, on ne laisse pas accepter dans le vide
  useEffect(() => {
    if (pendingChannel && !verified) setPendingChannel(null);
  }, [pendingChannel, verified]);

  if (denied) {
    return <AccessDenied description={t("contactSettings.orgDenied")} />;
  }
  if (query.isLoading) {
    return (
      <div className="space-y-3" aria-busy="true" data-testid="contact-settings-loading">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }
  if (query.isError || !settings) {
    // Refus du serveur (organisation suspendue ou archivée, rôle retiré) : le texte du refus, pas un échec réseau
    const denied403 = httpStatus(query.error) === 403;
    return (
      <ErrorState
        description={denied403 ? contactSettingsErrorMessage(query.error, { inOrganization: isOrganization }) : t("contactSettings.loadError")}
        onRetry={() => void query.refetch()}
        isRetrying={query.isFetching}
      />
    );
  }

  const toggle = async (channel: ContactChannel, enabled: boolean) => {
    setSwitchError(undefined);
    if (enabled && needsConsent(channel)) {
      setConsentError(undefined);
      setPendingChannel(channel);
      return;
    }
    try {
      await setChannel.mutateAsync({ channel, enabled });
      toast.success(t(enabled ? "contactSettings.channels.enabledToast" : "contactSettings.channels.disabledToast"));
    } catch (err) {
      setSwitchError(contactSettingsErrorMessage(err, { inOrganization: isOrganization }));
      if (isChannelNotAvailable(err)) void query.refetch(); // l'interrupteur serveur a changé : réaligner les canaux affichés
    }
  };

  const accept = async () => {
    if (!pendingChannel) return;
    setConsentError(undefined);
    try {
      await setChannel.mutateAsync({ channel: pendingChannel, enabled: true, textVersion: CONSENT_TEXT_VERSION });
      setPendingChannel(null);
      toast.success(t("contactSettings.channels.enabledToast"));
    } catch (err) {
      setConsentError(contactSettingsErrorMessage(err, { inOrganization: isOrganization }));
      if (isChannelNotAvailable(err)) {
        setPendingChannel(null);
        setSwitchError(contactSettingsErrorMessage(err));
        void query.refetch();
      }
    }
  };

  const channels = availableChannels(settings);
  const phoneChannels = channels.some((channel) => needsConsent(channel));

  return (
    <section aria-labelledby="contact-settings-title" className="space-y-4">
      <div>
        <h2 id="contact-settings-title" className="font-display text-lg font-bold">
          {isOrganization ? t("contactSettings.titleFor", { name: active.name }) : t("contactSettings.title")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("contactSettings.intro")}</p>
        {!phoneChannels && <p className="mt-2 text-sm text-muted-foreground">{t("contactSettings.orgMessageOnly")}</p>}
      </div>

      {phoneChannels && <PhoneBlock settings={settings} allowLoginPhone={!isOrganization} />}

      <section aria-labelledby="contact-channels-title" className="space-y-1 rounded-xl border p-4">
        <h3 id="contact-channels-title" className="font-semibold">
          {t("contactSettings.channels.title")}
        </h3>
        <ul className="divide-y">
          {CHANNELS.filter((channel) => channels.includes(channel)).map((channel) => {
            const locked = needsConsent(channel) && !verified;
            const hintId = `contact-channel-${channel}-hint`;
            return (
              <li key={channel} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <label htmlFor={`contact-channel-${channel}`} className="text-sm font-medium">
                    {t(`contactSettings.channels.${channel}`)}
                  </label>
                  <p id={hintId} className="text-xs text-muted-foreground">
                    {t(`contactSettings.channels.${channel}_hint`)}
                    {locked && ` ${t("contactSettings.channels.needsPhone")}`}
                  </p>
                </div>
                <Switch
                  id={`contact-channel-${channel}`}
                  checked={settings.channels[channel]?.enabled ?? false}
                  disabled={locked || setChannel.isPending}
                  aria-describedby={hintId}
                  onCheckedChange={(checked) => void toggle(channel, checked)}
                />
              </li>
            );
          })}
        </ul>
        <FormAlert message={switchError} />
      </section>

      <ConsentDialog
        channel={pendingChannel}
        masked={settings.phone?.masked ?? ""}
        pending={setChannel.isPending}
        error={consentError}
        onAccept={() => void accept()}
        onClose={() => setPendingChannel(null)}
      />
    </section>
  );
}
