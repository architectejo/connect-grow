import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { BadgeCheck, Loader2, LogOut, Phone, Save, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AccountShell } from "@/components/layout/AccountShell";
import { PageHeader } from "@/components/common";
import { ImageField } from "@/components/common/ImageField";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { errorProps, Field, fieldInputClass, FormAlert, PasswordInput, PhoneInput } from "@/components/auth/FormFields";
import { ContactSettingsSection } from "@/components/settings/ContactSettingsSection";
import { OtpStep } from "@/components/auth/OtpStep";
import { useAuth } from "@/contexts/AuthContext";
import { useChangePassword, useUpdateProfile } from "@/hooks/use-account";
import { useCities } from "@/hooks/use-marketplace";
import { useRequestOtp } from "@/hooks/use-otp";
import i18n from "@/i18n";
import { formatLocalPhone, localPhoneSchema, parseApiErrors, passwordSchema, toE164 } from "@/lib/validation";

// --- Profil ---

const profileSchema = z.object({
  full_name: z.string().trim().min(2, i18n.t("validation.fullNameRequired")).max(255),
  commune: z.string(),
});

function ProfileTab() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data: cities = [] } = useCities();
  const update = useUpdateProfile();
  const [photo, setPhoto] = useState<{ file: File; preview: string } | null>(null);
  const [error, setError] = useState<string>();

  const form = useForm<z.infer<typeof profileSchema>>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: user?.full_name ?? "", commune: user?.commune ? user.commune : "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setError(undefined);
    const data = new FormData();
    data.append("full_name", values.full_name.trim());
    if (values.commune) {
      data.append("commune", values.commune);
      const city = cities.find((c) => c.communes.some((commune) => commune.id === values.commune));
      if (city) data.append("ville", city.id);
    }
    if (photo) data.append("photo", photo.file);
    try {
      await update.mutateAsync(data);
      setPhoto(null);
      toast.success(t("settings.profileUpdated"));
    } catch (err) {
      const { fields, general } = parseApiErrors(err);
      if (fields.full_name) form.setError("full_name", { message: fields.full_name });
      // photo refusée : clé `photo` ; commune hors de la ville ou ville manquante : clés `commune` / `ville`
      setError(general ?? fields.photo ?? fields.commune ?? fields.ville ?? (fields.full_name ? undefined : t("settings.updateFailed")));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <ImageField
        label={t("imageField.photo")}
        src={photo?.preview ?? user?.photo}
        name={user?.full_name}
        shape="circle"
        onSelect={(file, preview) => setPhoto({ file, preview })}
      />
      <Field label={t("authForm.fullName")} htmlFor="full_name" error={form.formState.errors.full_name?.message}>
        <Input id="full_name" autoComplete="name" className={fieldInputClass} {...errorProps("full_name", form.formState.errors.full_name?.message)} {...form.register("full_name")} />
      </Field>
      <Field label={t("settings.communeLabel")} htmlFor="commune" hint={t("settings.communeHint")}>
        <Controller
          control={form.control}
          name="commune"
          render={({ field }) => (
            <CommuneSelect id="commune" value={field.value} onChange={field.onChange} allowAll={false} placeholder={t("settings.communePlaceholder")} className="h-12 rounded-xl bg-card" />
          )}
        />
      </Field>
      <FormAlert message={error} />
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />} {t("common.save")}
      </Button>
      <p className="border-t pt-4 text-sm">
        <Link to="/profiles" className="inline-flex items-center gap-2 font-semibold text-primary underline-offset-2 hover:underline">
          <Users className="h-4 w-4" aria-hidden /> {t("settings.manageProfiles")}
        </Link>
      </p>
    </form>
  );
}

// --- Téléphone : tout changement passe par un code SMS (CDC 3.1) ---

function ChangePhoneDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const requestOtp = useRequestOtp();
  const update = useUpdateProfile();
  const [step, setStep] = useState<"phone" | "otp">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!open) {
      setStep("phone");
      setCode("");
      setError(undefined);
    }
  }, [open]);

  const send = async () => {
    const valid = localPhoneSchema.safeParse(phone);
    if (!valid.success) {
      setError(valid.error.issues[0].message);
      return false;
    }
    // Un numéro déjà vérifié sur ce compte ne passe plus par un code : rien à confirmer
    if (user?.phone_verified && user.phone === toE164(phone)) {
      setError(t("settings.samePhone"));
      return false;
    }
    setError(undefined);
    try {
      await requestOtp.mutateAsync({ phone: toE164(phone), purpose: "REGISTER" });
      setCode("");
      setStep("otp");
      return true;
    } catch (err) {
      setError(parseApiErrors(err).general ?? t("authForm.register.resendFailed"));
      return false;
    }
  };

  const confirm = async () => {
    setError(undefined);
    try {
      await update.mutateAsync({ phone: toE164(phone), otp_code: code });
      toast.success(t("settings.phoneSaved"));
      onOpenChange(false);
    } catch (err) {
      const { fields, general } = parseApiErrors(err);
      setError(fields.otp_code ?? fields.phone ?? general ?? t("settings.verifyFailed"));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{step === "phone" ? t("settings.newPhone") : t("authForm.register.verifyTitle")}</DialogTitle>
          {step === "phone" && <DialogDescription>{t("settings.newPhoneDescription")}</DialogDescription>}
        </DialogHeader>
        {step === "phone" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="space-y-4"
          >
            <PhoneInput id="new-phone" value={phone} onChange={setPhone} invalid={!!error} autoFocus aria-label={t("settings.newPhone")} />
            <FormAlert message={error} />
            <Button type="submit" className="w-full" disabled={requestOtp.isPending}>
              {requestOtp.isPending && <Loader2 className="animate-spin" aria-hidden />} {t("authForm.forgot.receiveCode")}
            </Button>
          </form>
        ) : (
          <OtpStep
            phone={phone}
            code={code}
            onCodeChange={(value) => {
              setCode(value);
              setError(undefined);
            }}
            onSubmit={confirm}
            onResend={async () => {
              if (!(await send())) throw new Error(t("authForm.forgot.resendFailed"));
            }}
            onChangeNumber={() => setStep("phone")}
            isSubmitting={update.isPending}
            error={error}
            submitLabel={t("settings.confirmPhone")}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ContactTab() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const localPhone = user?.phone?.replace(/^\+243/, "");

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Phone className="h-5 w-5" aria-hidden />
        </span>
        <div className="flex-1">
          <p className="text-sm text-muted-foreground">{t("authForm.phone")}</p>
          <p className="font-semibold">{localPhone ? `+243 ${formatLocalPhone(localPhone)}` : t("settings.noPhone")}</p>
          {user?.phone && user.phone_verified && (
            <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-success">
              <BadgeCheck className="h-3.5 w-3.5" aria-hidden /> {t("settings.verifiedBySms")}
            </p>
          )}
        </div>
        <Button variant="outline" onClick={() => setOpen(true)}>
          {user?.phone ? t("settings.changePhone") : t("settings.addPhone")}
        </Button>
      </div>
      <div className="rounded-xl border p-4">
        <p className="text-sm text-muted-foreground">{t("authForm.email")}</p>
        <p className="font-semibold">{user?.email || t("settings.noEmail")}</p>
      </div>
      <p className="text-xs text-muted-foreground">
        {t("settings.phonePurpose")}
      </p>
      <ChangePhoneDialog open={open} onOpenChange={setOpen} />
      <ContactSettingsSection />
    </div>
  );
}

// --- Sécurité ---

const passwordFormSchema = z
  .object({ old_password: z.string().min(1, i18n.t("settings.currentPasswordRequired")), new_password: passwordSchema, confirm: z.string() })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: i18n.t("validation.passwordMismatch") })
  .refine((v) => v.new_password !== v.old_password, { path: ["new_password"], message: i18n.t("settings.differentPassword") });

function SecurityTab() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { logout, endSession } = useAuth();
  const [confirmAll, setConfirmAll] = useState(false);
  const changePassword = useChangePassword();
  const [error, setError] = useState<string>();
  const form = useForm<z.infer<typeof passwordFormSchema>>({
    resolver: zodResolver(passwordFormSchema),
    defaultValues: { old_password: "", new_password: "", confirm: "" },
  });
  const [oldPassword, newPassword, confirm] = form.watch(["old_password", "new_password", "confirm"]);
  const errors = form.formState.errors;

  const onSubmit = form.handleSubmit(async ({ old_password, new_password }) => {
    setError(undefined);
    try {
      await changePassword.mutateAsync({ old_password, new_password });
      form.reset();
      // Le serveur révoque toutes les sessions au changement de mot de passe : on repart de la connexion
      toast.success(t("settings.passwordChanged"));
      endSession(); // sessions déjà révoquées par le serveur : purge locale seule, sans appeler logout/
      navigate("/login", { replace: true });
    } catch (err) {
      const { general } = parseApiErrors(err);
      if (general && /ancien/i.test(general)) form.setError("old_password", { message: general });
      else setError(general ?? t("settings.changeFailed"));
    }
  });

  return (
    <div className="space-y-8">
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <h2 className="font-bold">{t("settings.changePasswordTitle")}</h2>
        <Field label={t("settings.currentPassword")} htmlFor="old_password" error={errors.old_password?.message}>
          <PasswordInput id="old_password" autoComplete="current-password" value={oldPassword} {...errorProps("old_password", errors.old_password?.message)} {...form.register("old_password")} />
        </Field>
        <Field label={t("authForm.newPassword")} htmlFor="new_password" error={errors.new_password?.message}>
          <PasswordInput id="new_password" autoComplete="new-password" showStrength value={newPassword} {...errorProps("new_password", errors.new_password?.message)} {...form.register("new_password")} />
        </Field>
        <Field label={t("settings.confirmNewPassword")} htmlFor="confirm" error={errors.confirm?.message}>
          <PasswordInput id="confirm" autoComplete="new-password" value={confirm} {...errorProps("confirm", errors.confirm?.message)} {...form.register("confirm")} />
        </Field>
        <FormAlert message={error} />
        <Button type="submit" disabled={changePassword.isPending}>
          {changePassword.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />} {t("settings.updatePassword")}
        </Button>
      </form>

      <div className="border-t pt-6">
        <Button
          variant="ghost"
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => {
            logout();
            navigate("/", { replace: true });
          }}
        >
          <LogOut aria-hidden /> {t("settings.logout")}
        </Button>
        <Button
          variant="ghost"
          className="ml-2 text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => setConfirmAll(true)}
        >
          <LogOut aria-hidden /> {t("settings.logoutAll")}
        </Button>
        <AlertDialog open={confirmAll} onOpenChange={setConfirmAll}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("settings.logoutAllTitle")}</AlertDialogTitle>
              <AlertDialogDescription>{t("settings.logoutAllDescription")}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
              <AlertDialogAction
                onClick={async () => {
                  await logout({ all: true });
                  navigate("/", { replace: true });
                }}
              >
                {t("settings.logoutAllConfirm")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}

const TABS = ["profile", "contact", "security"] as const;

const Settings = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const tab = TABS.find((value) => value === requested) ?? "profile";

  return (
    <AccountShell>
      <PageHeader title={t("settings.title")} description={t("settings.description")} />
      <Tabs value={tab} onValueChange={(value) => setSearchParams(value === "profile" ? {} : { tab: value }, { replace: true })}>
        <TabsList className="mb-6 h-auto w-full justify-start gap-1 overflow-x-auto rounded-xl bg-muted p-1 scrollbar-none sm:w-auto">
          <TabsTrigger value="profile" className="rounded-lg px-4 py-2">{t("settings.tabProfile")}</TabsTrigger>
          <TabsTrigger value="contact" className="rounded-lg px-4 py-2">{t("settings.tabContact")}</TabsTrigger>
          <TabsTrigger value="security" className="rounded-lg px-4 py-2">{t("settings.tabSecurity")}</TabsTrigger>
        </TabsList>
        <div className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
          <TabsContent value="profile" className="mt-0">
            <ProfileTab />
          </TabsContent>
          <TabsContent value="contact" className="mt-0">
            <ContactTab />
          </TabsContent>
          <TabsContent value="security" className="mt-0">
            <SecurityTab />
          </TabsContent>
        </div>
      </Tabs>
    </AccountShell>
  );
};

export default Settings;
