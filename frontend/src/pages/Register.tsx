import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check, Loader2, Mail, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "@/api/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { errorProps, Field, fieldInputClass, FormAlert, MethodToggle, PasswordInput, PhoneInput } from "@/components/auth/FormFields";
import { OtpStep } from "@/components/auth/OtpStep";
import { useAuth } from "@/contexts/AuthContext";
import { useRequestOtp } from "@/hooks/use-otp";
import { loginPath, safeNext } from "@/lib/auth-paths";
import { cn } from "@/lib/utils";
import i18n from "@/i18n";
import { emailSchema, localPhoneSchema, parseApiErrors, passwordSchema, toE164 } from "@/lib/validation";

type Method = "phone" | "email";

const schema = z
  .object({
    fullName: z.string().trim().min(2, i18n.t("validation.fullNameRequired")).max(255),
    method: z.enum(["phone", "email"]),
    phone: z.string(),
    email: z.string(),
    password: passwordSchema,
    acceptTerms: z.boolean().refine(Boolean, i18n.t("validation.termsRequired")),
  })
  .superRefine((values, ctx) => {
    const result = values.method === "phone" ? localPhoneSchema.safeParse(values.phone) : emailSchema.safeParse(values.email);
    if (!result.success) ctx.addIssue({ code: "custom", path: [values.method], message: result.error.issues[0].message });
  });

type FormValues = z.infer<typeof schema>;

const methods = [
  { value: "phone" as const, labelKey: "authForm.phone", icon: Smartphone },
  { value: "email" as const, labelKey: "authForm.email", icon: Mail },
];

// Champs renvoyés par l'API → champs du formulaire
const API_FIELD_MAP: Record<string, keyof FormValues> = {
  email: "email",
  phone: "phone",
  full_name: "fullName",
  password: "password",
};

function Stepper({ step }: { step: 1 | 2 }) {
  const { t } = useTranslation();
  const steps = [t("authForm.register.stepAccount"), t("authForm.register.stepVerify")];
  return (
    <ol className="mb-8 flex items-center gap-3" aria-label={t("authForm.register.steps")}>
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
  // La destination (ex. une invitation d'organisation) survit au passage par la connexion
  const loginLink = next !== "/dashboard" ? loginPath(next) : "/login";
  const { login, isAuthenticated } = useAuth();
  const requestOtp = useRequestOtp();
  const { t } = useTranslation();

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
      fullName: "",
      method: "phone",
      phone: "",
      email: "",
      password: "",
      acceptTerms: false,
    },
  });
  const [method, password, phone] = watch(["method", "password", "phone"]);

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
      ...(values.method === "phone" ? { phone: toE164(values.phone), otp_code: code } : { email: values.email.trim() }),
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
      setGeneralError(general ?? (mapped ? undefined : t("authForm.register.failed")));
      return false;
    }

    try {
      await login(values.method === "phone" ? { phone: toE164(values.phone), password: values.password } : { email: values.email.trim(), password: values.password });
      // Un seul type de compte (règle 1) : les profils s'ajoutent ensuite depuis « Mes profils »
      toast.success(t("register.welcomeTitle"), { description: t("register.welcomeDescription") });
      navigate(next, { replace: true });
    } catch {
      // Compte créé mais connexion automatique impossible : l'utilisateur se connecte lui-même
      toast.success(t("authForm.register.createdLogin"));
      navigate(loginLink, { replace: true });
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
      // Réponse neutre côté serveur : aucune indication « numéro déjà utilisé » à ce stade
      setGeneralError(general ?? fields.phone ?? t("authForm.register.sendFailed"));
    }
  };

  const onOtpSubmit = async () => {
    setOtpError(undefined);
    await createAccount(getValues(), otpCode);
  };

  return (
    <AuthLayout
      title={step === 1 ? t("authForm.register.title") : t("authForm.register.verifyTitle")}
      description={step === 1 ? t("authForm.register.description") : undefined}
      footer={
        step === 1 && (
          <>
            {t("authForm.register.alreadyMember")}{" "}
            <Link to={loginLink} className="font-semibold text-primary hover:underline">
              {t("authForm.register.login")}
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
              setOtpError(parseApiErrors(error).general ?? t("authForm.register.resendFailed"));
              throw error;
            })
          }
          onChangeNumber={() => setStep(1)}
          isSubmitting={isCreating}
          error={otpError}
          submitLabel={t("authForm.register.verifySubmit")}
        />
      ) : (
        <form onSubmit={handleSubmit(onAccountSubmit)} noValidate className="space-y-5">
          <Field label={t("authForm.fullName")} htmlFor="fullName" error={errors.fullName?.message}>
            <Input
              id="fullName"
              autoComplete="name"
              placeholder={t("authForm.fullNamePlaceholder")}
              className={fieldInputClass}
              {...errorProps("fullName", errors.fullName?.message)}
              {...register("fullName")}
            />
          </Field>

          <div className="space-y-3">
            <p className="text-sm font-semibold">{t("authForm.register.registerWith")}</p>
            <MethodToggle<Method>
              label={t("authForm.register.registerWith")}
              value={method}
              onChange={(value) => setValue("method", value)}
              options={methods.map(({ labelKey, ...rest }) => ({ ...rest, label: t(labelKey) }))}
            />
          </div>

          {method === "phone" ? (
            <Field label={t("authForm.phoneLabel")} htmlFor="phone" error={errors.phone?.message} hint={t("authForm.register.phoneHint")}>
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
            <Field label={t("authForm.emailLabel")} htmlFor="email" error={errors.email?.message}>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder={t("authForm.emailPlaceholder")}
                className={fieldInputClass}
                {...errorProps("email", errors.email?.message)}
                {...register("email")}
              />
            </Field>
          )}

          <Field label={t("authForm.passwordLabel")} htmlFor="password" error={errors.password?.message} hint={t("authForm.register.passwordHint")}>
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
                {t("authForm.register.acceptTerms")}
              </label>
            </div>
            {errors.acceptTerms && (
              <p id="acceptTerms-error" role="alert" className="text-sm font-medium text-destructive">
                {errors.acceptTerms.message}
              </p>
            )}
          </div>

          <p className="text-sm text-muted-foreground">{t("register.oneAccount")}</p>

          <FormAlert message={generalError} />

          <Button type="submit" size="lg" className="w-full shadow-glow" disabled={isSubmitting || isCreating}>
            {(isSubmitting || isCreating) && <Loader2 className="animate-spin" aria-hidden />}
            {method === "phone" ? t("authForm.register.sendCode") : t("authForm.register.submit")}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
};

export default Register;
