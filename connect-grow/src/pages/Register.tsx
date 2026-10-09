import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Building2, Check, Loader2, Mail, Smartphone, UserRound } from "lucide-react";
import { toast } from "sonner";
import apiClient from "@/api/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { errorProps, Field, fieldInputClass, FormAlert, MethodToggle, PasswordInput, PhoneInput } from "@/components/auth/FormFields";
import { OtpStep } from "@/components/auth/OtpStep";
import { useAuth } from "@/contexts/AuthContext";
import { useRequestOtp } from "@/hooks/use-otp";
import { safeNext } from "@/lib/auth-paths";
import { cn } from "@/lib/utils";
import { emailSchema, localPhoneSchema, parseApiErrors, passwordSchema, toE164 } from "@/lib/validation";

type Method = "phone" | "email";
type UserType = "PARTICULIER" | "ENTREPRISE";

const schema = z
  .object({
    userType: z.enum(["PARTICULIER", "ENTREPRISE"]),
    fullName: z.string().trim().min(2, "Saisissez votre nom complet.").max(255),
    businessName: z.string().trim(),
    method: z.enum(["phone", "email"]),
    phone: z.string(),
    email: z.string(),
    password: passwordSchema,
    acceptTerms: z.boolean().refine(Boolean, "Vous devez accepter les conditions pour continuer."),
  })
  .superRefine((values, ctx) => {
    const result = values.method === "phone" ? localPhoneSchema.safeParse(values.phone) : emailSchema.safeParse(values.email);
    if (!result.success) ctx.addIssue({ code: "custom", path: [values.method], message: result.error.issues[0].message });
    if (values.userType === "ENTREPRISE" && values.businessName.length < 2)
      ctx.addIssue({ code: "custom", path: ["businessName"], message: "Saisissez le nom de votre entreprise." });
  });

type FormValues = z.infer<typeof schema>;

const methods = [
  { value: "phone" as const, label: "Téléphone", icon: Smartphone },
  { value: "email" as const, label: "E-mail", icon: Mail },
];

const accountTypes: { value: UserType; title: string; description: string; icon: typeof UserRound }[] = [
  { value: "PARTICULIER", title: "Particulier", description: "Acheter, vendre, troquer", icon: UserRound },
  { value: "ENTREPRISE", title: "Entreprise", description: "Boutique, artisan, prestataire", icon: Building2 },
];

// Champs renvoyés par l'API → champs du formulaire
const API_FIELD_MAP: Record<string, keyof FormValues> = {
  email: "email",
  phone: "phone",
  full_name: "fullName",
  password: "password",
};

function Stepper({ step }: { step: 1 | 2 }) {
  const steps = ["Votre compte", "Vérification"];
  return (
    <ol className="mb-8 flex items-center gap-3" aria-label="Étapes de l'inscription">
      {steps.map((label, i) => {
        const index = (i + 1) as 1 | 2;
        const done = index < step;
        const current = index === step;
        return (
          <li key={label} className="flex flex-1 items-center gap-2" aria-current={current ? "step" : undefined}>
            <span
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                done ? "bg-success text-success-foreground" : current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
              )}
            >
              {done ? <Check className="h-4 w-4" aria-hidden /> : index}
            </span>
            <span className={cn("text-sm font-semibold", current ? "text-foreground" : "text-muted-foreground")}>{label}</span>
            {i < steps.length - 1 && <span className="h-px flex-1 bg-border" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

const Register = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const { login, isAuthenticated } = useAuth();
  const requestOtp = useRequestOtp();

  const [step, setStep] = useState<1 | 2>(1);
  const [otpCode, setOtpCode] = useState("");
  const [otpError, setOtpError] = useState<string>();
  const [generalError, setGeneralError] = useState<string>();
  const [isCreating, setIsCreating] = useState(false);

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    setError,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      userType: "PARTICULIER",
      fullName: "",
      businessName: "",
      method: "phone",
      phone: "",
      email: "",
      password: "",
      acceptTerms: false,
    },
  });
  const [userType, method, password, phone] = watch(["userType", "method", "password", "phone"]);

  useEffect(() => {
    // Déjà connecté (hors création en cours) : pas besoin de s'inscrire
    if (isAuthenticated && !isCreating) navigate(next, { replace: true });
  }, [isAuthenticated, isCreating, navigate, next]);

  /** Crée le compte puis connecte l'utilisateur. Renvoie false si l'API a refusé les données. */
  const createAccount = async (values: FormValues, code?: string) => {
    setIsCreating(true);
    const payload: Record<string, unknown> = {
      full_name: values.fullName.trim(),
      password: values.password,
      user_type: values.userType,
      ...(values.method === "phone" ? { phone: toE164(values.phone), otp_code: code } : { email: values.email.trim() }),
      ...(values.userType === "ENTREPRISE" && { business_profile: { business_name: values.businessName.trim() } }),
    };

    try {
      await apiClient.post("accounts/register/", payload);
    } catch (error) {
      setIsCreating(false);
      const { fields, general } = parseApiErrors(error);
      if (fields.otp_code) {
        setOtpError(fields.otp_code);
        return false;
      }
      // Erreur sur les informations du compte : retour à la première étape, erreurs sur les champs
      setStep(1);
      let mapped = false;
      for (const [apiField, message] of Object.entries(fields)) {
        const field = API_FIELD_MAP[apiField];
        if (field) {
          setError(field, { message });
          mapped = true;
        }
      }
      setGeneralError(general ?? (mapped ? undefined : "L'inscription a échoué. Vérifiez vos informations."));
      return false;
    }

    try {
      await login(values.method === "phone" ? { phone: toE164(values.phone), password: values.password } : { email: values.email.trim(), password: values.password });
      toast.success("Bienvenue sur Connecte+ !", {
        description:
          values.userType === "ENTREPRISE"
            ? "Pensez à envoyer vos documents pour obtenir le badge Vérifié."
            : "Votre compte est prêt.",
      });
      navigate(next, { replace: true });
    } catch {
      // Compte créé mais connexion automatique impossible : l'utilisateur se connecte lui-même
      toast.success("Compte créé. Connectez-vous pour continuer.");
      navigate("/login", { replace: true });
    } finally {
      setIsCreating(false);
    }
    return true;
  };

  const onAccountSubmit = async (values: FormValues) => {
    setGeneralError(undefined);
    if (values.method === "email") {
      await createAccount(values);
      return;
    }
    try {
      await requestOtp.mutateAsync({ phone: toE164(values.phone), purpose: "REGISTER" });
      setOtpCode("");
      setOtpError(undefined);
      setStep(2);
    } catch (error) {
      const { fields, general } = parseApiErrors(error);
      const message = general ?? fields.phone;
      if (message && /compte existe/i.test(message)) setError("phone", { message });
      else setGeneralError(message ?? "L'envoi du code a échoué. Réessayez.");
    }
  };

  const onOtpSubmit = async () => {
    setOtpError(undefined);
    await createAccount(getValues(), otpCode);
  };

  return (
    <AuthLayout
      title={step === 1 ? "Créer votre compte" : "Vérifiez votre numéro"}
      description={step === 1 ? "Gratuit, en moins d'une minute." : undefined}
      footer={
        step === 1 && (
          <>
            Déjà inscrit ?{" "}
            <Link to="/login" className="font-semibold text-primary hover:underline">
              Se connecter
            </Link>
          </>
        )
      }
    >
      {method === "phone" && <Stepper step={step} />}

      {step === 2 ? (
        <OtpStep
          phone={phone}
          code={otpCode}
          onCodeChange={(code) => {
            setOtpCode(code);
            setOtpError(undefined);
          }}
          onSubmit={onOtpSubmit}
          onResend={() =>
            requestOtp.mutateAsync({ phone: toE164(phone), purpose: "REGISTER" }).catch((error) => {
              setOtpError(parseApiErrors(error).general ?? "L'envoi du code a échoué.");
              throw error;
            })
          }
          onChangeNumber={() => setStep(1)}
          isSubmitting={isCreating}
          error={otpError}
          submitLabel="Vérifier et créer mon compte"
        />
      ) : (
        <form onSubmit={handleSubmit(onAccountSubmit)} noValidate className="space-y-5">
          <fieldset>
            <legend className="mb-2 text-sm font-semibold">Vous êtes</legend>
            <div role="radiogroup" className="grid grid-cols-2 gap-3">
              {accountTypes.map(({ value, title, description, icon: Icon }) => {
                const selected = userType === value;
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setValue("userType", value)}
                    className={cn(
                      "relative flex flex-col items-start gap-2 rounded-xl border-2 p-3.5 text-left transition-colors",
                      selected ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/40",
                    )}
                  >
                    <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg", selected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <span>
                      <span className="block text-sm font-bold">{title}</span>
                      <span className="block text-xs text-muted-foreground">{description}</span>
                    </span>
                    {selected && <Check className="absolute right-3 top-3 h-4 w-4 text-primary" aria-hidden />}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <Field label="Nom complet" htmlFor="fullName" error={errors.fullName?.message}>
            <Input
              id="fullName"
              autoComplete="name"
              placeholder="Ex. : Grâce Mbuyi"
              className={fieldInputClass}
              {...errorProps("fullName", errors.fullName?.message)}
              {...register("fullName")}
            />
          </Field>

          {userType === "ENTREPRISE" && (
            <Field
              label="Nom de l'entreprise"
              htmlFor="businessName"
              error={errors.businessName?.message}
              hint="Le badge Vérifié s'obtient ensuite en envoyant vos documents (RCCM, identité du gérant)."
            >
              <Input
                id="businessName"
                autoComplete="organization"
                placeholder="Ex. : Boutique Ma Campagne"
                className={fieldInputClass}
                {...errorProps("businessName", errors.businessName?.message)}
                {...register("businessName")}
              />
            </Field>
          )}

          <div className="space-y-3">
            <p className="text-sm font-semibold">S'inscrire avec</p>
            <MethodToggle<Method> label="S'inscrire avec" value={method} onChange={(value) => setValue("method", value)} options={methods} />
          </div>

          {method === "phone" ? (
            <Field label="Numéro de téléphone" htmlFor="phone" error={errors.phone?.message} hint="Nous vous enverrons un code par SMS pour le vérifier.">
              <Controller
                control={control}
                name="phone"
                render={({ field }) => (
                  <PhoneInput
                    id="phone"
                    value={field.value}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                    invalid={!!errors.phone}
                    {...errorProps("phone", errors.phone?.message)}
                  />
                )}
              />
            </Field>
          ) : (
            <Field label="Adresse e-mail" htmlFor="email" error={errors.email?.message}>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="nom@exemple.com"
                className={fieldInputClass}
                {...errorProps("email", errors.email?.message)}
                {...register("email")}
              />
            </Field>
          )}

          <Field label="Mot de passe" htmlFor="password" error={errors.password?.message} hint="8 caractères minimum, avec au moins une lettre et un chiffre.">
            <PasswordInput
              id="password"
              autoComplete="new-password"
              showStrength
              value={password}
              {...errorProps("password", errors.password?.message)}
              {...register("password")}
            />
          </Field>

          <div className="space-y-2">
            <div className="flex items-start gap-3">
              <Controller
                control={control}
                name="acceptTerms"
                render={({ field }) => (
                  <Checkbox
                    id="acceptTerms"
                    checked={field.value}
                    onCheckedChange={(checked) => field.onChange(checked === true)}
                    className="mt-0.5 h-5 w-5 rounded-md"
                    {...errorProps("acceptTerms", errors.acceptTerms?.message)}
                  />
                )}
              />
              <label htmlFor="acceptTerms" className="text-sm leading-relaxed text-muted-foreground">
                J'accepte les conditions générales d'utilisation et la politique de confidentialité de Connecte+.
              </label>
            </div>
            {errors.acceptTerms && (
              <p id="acceptTerms-error" role="alert" className="text-sm font-medium text-destructive">
                {errors.acceptTerms.message}
              </p>
            )}
          </div>

          <FormAlert message={generalError} />

          <Button type="submit" size="lg" className="w-full shadow-glow" disabled={isSubmitting || isCreating}>
            {(isSubmitting || isCreating) && <Loader2 className="animate-spin" aria-hidden />}
            {method === "phone" ? "Recevoir le code par SMS" : "Créer mon compte"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
};

export default Register;
