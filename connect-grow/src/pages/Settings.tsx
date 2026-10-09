import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { BadgeCheck, Camera, Loader2, LogOut, Phone, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AccountShell } from "@/components/layout/AccountShell";
import { PageHeader, StatusBadge, UserAvatar } from "@/components/common";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { errorProps, Field, fieldInputClass, FormAlert, PasswordInput, PhoneInput } from "@/components/auth/FormFields";
import { OtpStep } from "@/components/auth/OtpStep";
import { useAuth } from "@/contexts/AuthContext";
import { useChangePassword, useUpdateProfile } from "@/hooks/use-account";
import { useCities } from "@/hooks/use-marketplace";
import { useRequestOtp } from "@/hooks/use-otp";
import { compressImage } from "@/lib/image";
import { formatLocalPhone, localPhoneSchema, parseApiErrors, passwordSchema, toE164 } from "@/lib/validation";

const BIO_MAX = 500;

/** Choix d'image (photo, logo) avec aperçu local et compression. */
function ImageField({
  label,
  src,
  name,
  shape,
  onSelect,
}: {
  label: string;
  src?: string | null;
  name?: string;
  shape: "circle" | "square";
  onSelect: (file: File, preview: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="flex items-center gap-4">
      <UserAvatar src={src} name={name} size="xl" shape={shape} />
      <div>
        <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>
          <Camera aria-hidden /> {label}
        </Button>
        <p className="mt-1.5 text-xs text-muted-foreground">JPG, PNG ou WebP · optimisée automatiquement</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        tabIndex={-1}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          const compressed = await compressImage(file);
          onSelect(compressed, URL.createObjectURL(compressed));
        }}
      />
    </div>
  );
}

// --- Profil ---

const profileSchema = z.object({
  full_name: z.string().trim().min(2, "Saisissez votre nom complet.").max(255),
  commune: z.string(),
});

function ProfileTab() {
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
      toast.success("Profil mis à jour.");
    } catch (err) {
      const { fields, general } = parseApiErrors(err);
      if (fields.full_name) form.setError("full_name", { message: fields.full_name });
      // photo refusée : clé `photo` ; commune hors de la ville ou ville manquante : clés `commune` / `ville`
      setError(general ?? fields.photo ?? fields.commune ?? fields.ville ?? (fields.full_name ? undefined : "La mise à jour a échoué."));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <ImageField
        label="Changer la photo"
        src={photo?.preview ?? user?.photo}
        name={user?.full_name}
        shape="circle"
        onSelect={(file, preview) => setPhoto({ file, preview })}
      />
      <Field label="Nom complet" htmlFor="full_name" error={form.formState.errors.full_name?.message}>
        <Input id="full_name" autoComplete="name" className={fieldInputClass} {...errorProps("full_name", form.formState.errors.full_name?.message)} {...form.register("full_name")} />
      </Field>
      <Field label="Commune" htmlFor="commune" hint="Affichée sur votre profil public pour situer vos annonces.">
        <Controller
          control={form.control}
          name="commune"
          render={({ field }) => (
            <CommuneSelect id="commune" value={field.value} onChange={field.onChange} allowAll={false} placeholder="Choisissez votre commune" className="h-12 rounded-xl bg-card" />
          )}
        />
      </Field>
      <FormAlert message={error} />
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />} Enregistrer
      </Button>
    </form>
  );
}

// --- Boutique (comptes entreprise) ---

const shopSchema = z.object({
  business_name: z.string().trim().min(2, "Saisissez le nom de votre entreprise.").max(255),
  bio: z.string().max(BIO_MAX, `${BIO_MAX} caractères maximum.`),
  nif: z.string().max(50),
});

function ShopTab() {
  const { user } = useAuth();
  const update = useUpdateProfile();
  const profile = user?.business_profile;
  const [logo, setLogo] = useState<{ file: File; preview: string } | null>(null);
  const [error, setError] = useState<string>();

  const form = useForm<z.infer<typeof shopSchema>>({
    resolver: zodResolver(shopSchema),
    defaultValues: { business_name: profile?.business_name ?? "", bio: profile?.bio ?? "", nif: profile?.nif ?? "" },
  });
  const bio = form.watch("bio");

  const onSubmit = form.handleSubmit(async (values) => {
    setError(undefined);
    // Notation pointée comprise par DRF pour le profil imbriqué en multipart
    const data = new FormData();
    data.append("business_profile.business_name", values.business_name.trim());
    data.append("business_profile.bio", values.bio.trim());
    data.append("business_profile.nif", values.nif.trim());
    if (logo) data.append("business_profile.logo", logo.file);
    try {
      await update.mutateAsync(data);
      setLogo(null);
      toast.success("Boutique mise à jour.");
    } catch (err) {
      const { fields, general } = parseApiErrors(err);
      // Image refusée (format, poids, plus de 16 millions de pixels) : clé `logo`
      setError(general ?? fields.logo ?? fields.business_name ?? fields.bio ?? fields.nif ?? "La mise à jour a échoué.");
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <div className="flex items-center gap-2">
        {profile?.is_verified ? (
          <StatusBadge kind="verified" size="md" />
        ) : (
          <span className="rounded-full bg-muted px-2.5 py-1.5 text-xs font-semibold text-muted-foreground">Boutique non vérifiée</span>
        )}
      </div>
      <ImageField
        label="Changer le logo"
        src={logo?.preview ?? profile?.logo}
        name={profile?.business_name}
        shape="square"
        onSelect={(file, preview) => setLogo({ file, preview })}
      />
      <Field label="Nom de l'entreprise" htmlFor="business_name" error={form.formState.errors.business_name?.message}>
        <Input id="business_name" autoComplete="organization" className={fieldInputClass} {...errorProps("business_name", form.formState.errors.business_name?.message)} {...form.register("business_name")} />
      </Field>
      <Field
        label="Présentation"
        htmlFor="bio"
        error={form.formState.errors.bio?.message}
        aside={<span className="text-xs tabular-nums text-muted-foreground">{bio.length}/{BIO_MAX}</span>}
        hint="Activité, spécialités, horaires, lieu de retrait… Elle apparaît sur votre vitrine."
      >
        <Textarea id="bio" maxLength={BIO_MAX} className="min-h-[120px] rounded-xl bg-card" {...form.register("bio")} />
      </Field>
      <Field label="Numéro d'identification fiscale (NIF)" htmlFor="nif" hint="Facultatif. Non affiché publiquement.">
        <Input id="nif" className={fieldInputClass} {...form.register("nif")} />
      </Field>
      <FormAlert message={error} />
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />} Enregistrer
      </Button>
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
      setError(parseApiErrors(err).general ?? "L'envoi du code a échoué.");
      return false;
    }
  };

  const confirm = async () => {
    setError(undefined);
    try {
      await update.mutateAsync({ phone: toE164(phone), otp_code: code });
      toast.success("Numéro vérifié et enregistré.");
      onOpenChange(false);
    } catch (err) {
      const { fields, general } = parseApiErrors(err);
      setError(fields.otp_code ?? fields.phone ?? general ?? "La vérification a échoué.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{step === "phone" ? "Nouveau numéro" : "Vérifiez votre numéro"}</DialogTitle>
          {step === "phone" && <DialogDescription>Nous enverrons un code par SMS pour confirmer ce numéro.</DialogDescription>}
        </DialogHeader>
        {step === "phone" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="space-y-4"
          >
            <PhoneInput id="new-phone" value={phone} onChange={setPhone} invalid={!!error} autoFocus aria-label="Nouveau numéro" />
            <FormAlert message={error} />
            <Button type="submit" className="w-full" disabled={requestOtp.isPending}>
              {requestOtp.isPending && <Loader2 className="animate-spin" aria-hidden />} Recevoir le code
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
              if (!(await send())) throw new Error("Échec du renvoi");
            }}
            onChangeNumber={() => setStep("phone")}
            isSubmitting={update.isPending}
            error={error}
            submitLabel="Confirmer ce numéro"
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ContactTab() {
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
          <p className="text-sm text-muted-foreground">Téléphone</p>
          <p className="font-semibold">{localPhone ? `+243 ${formatLocalPhone(localPhone)}` : "Aucun numéro"}</p>
          {user?.phone && user.phone_verified && (
            <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-success">
              <BadgeCheck className="h-3.5 w-3.5" aria-hidden /> Vérifié par SMS
            </p>
          )}
        </div>
        <Button variant="outline" onClick={() => setOpen(true)}>
          {user?.phone ? "Changer de numéro" : "Ajouter un numéro"}
        </Button>
      </div>
      <div className="rounded-xl border p-4">
        <p className="text-sm text-muted-foreground">E-mail</p>
        <p className="font-semibold">{user?.email || "Aucune adresse e-mail"}</p>
      </div>
      <p className="text-xs text-muted-foreground">
        Votre numéro permet aux acheteurs de vous appeler ou de vous écrire sur WhatsApp, et sert à réinitialiser votre mot de passe.
      </p>
      <ChangePhoneDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

// --- Sécurité ---

const passwordFormSchema = z
  .object({ old_password: z.string().min(1, "Saisissez votre mot de passe actuel."), new_password: passwordSchema, confirm: z.string() })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Les deux mots de passe ne correspondent pas." })
  .refine((v) => v.new_password !== v.old_password, { path: ["new_password"], message: "Choisissez un mot de passe différent de l'actuel." });

function SecurityTab() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { logout } = useAuth();
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
      logout();
      navigate("/login", { replace: true });
    } catch (err) {
      const { general } = parseApiErrors(err);
      if (general && /ancien/i.test(general)) form.setError("old_password", { message: general });
      else setError(general ?? "La modification a échoué.");
    }
  });

  return (
    <div className="space-y-8">
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <h2 className="font-bold">Changer de mot de passe</h2>
        <Field label="Mot de passe actuel" htmlFor="old_password" error={errors.old_password?.message}>
          <PasswordInput id="old_password" autoComplete="current-password" value={oldPassword} {...errorProps("old_password", errors.old_password?.message)} {...form.register("old_password")} />
        </Field>
        <Field label="Nouveau mot de passe" htmlFor="new_password" error={errors.new_password?.message}>
          <PasswordInput id="new_password" autoComplete="new-password" showStrength value={newPassword} {...errorProps("new_password", errors.new_password?.message)} {...form.register("new_password")} />
        </Field>
        <Field label="Confirmer le nouveau mot de passe" htmlFor="confirm" error={errors.confirm?.message}>
          <PasswordInput id="confirm" autoComplete="new-password" value={confirm} {...errorProps("confirm", errors.confirm?.message)} {...form.register("confirm")} />
        </Field>
        <FormAlert message={error} />
        <Button type="submit" disabled={changePassword.isPending}>
          {changePassword.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />} Mettre à jour
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
          <LogOut aria-hidden /> Se déconnecter
        </Button>
        <Button
          variant="ghost"
          className="ml-2 text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => {
            logout({ all: true });
            navigate("/", { replace: true });
          }}
        >
          <LogOut aria-hidden /> {t("settings.logoutAll")}
        </Button>
      </div>
    </div>
  );
}

const Settings = () => {
  const { user } = useAuth();
  const isBusiness = user?.user_type === "ENTREPRISE";

  return (
    <AccountShell>
      <PageHeader title="Paramètres" description="Gérez votre profil public, vos coordonnées et la sécurité de votre compte." />
      <Tabs defaultValue="profile">
        <TabsList className="mb-6 h-auto w-full justify-start gap-1 overflow-x-auto rounded-xl bg-muted p-1 scrollbar-none sm:w-auto">
          <TabsTrigger value="profile" className="rounded-lg px-4 py-2">Profil</TabsTrigger>
          {isBusiness && <TabsTrigger value="shop" className="rounded-lg px-4 py-2">Boutique</TabsTrigger>}
          <TabsTrigger value="contact" className="rounded-lg px-4 py-2">Coordonnées</TabsTrigger>
          <TabsTrigger value="security" className="rounded-lg px-4 py-2">Sécurité</TabsTrigger>
        </TabsList>
        <div className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
          <TabsContent value="profile" className="mt-0">
            <ProfileTab />
          </TabsContent>
          {isBusiness && (
            <TabsContent value="shop" className="mt-0">
              <ShopTab />
            </TabsContent>
          )}
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
