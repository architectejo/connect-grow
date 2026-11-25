import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Mail, Smartphone } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { errorProps, Field, fieldInputClass, FormAlert, MethodToggle, PasswordInput, PhoneInput } from "@/components/auth/FormFields";
import { useAuth } from "@/contexts/AuthContext";
import { safeNext } from "@/lib/auth-paths";
import { emailSchema, localPhoneSchema, parseApiErrors, toE164 } from "@/lib/validation";

type Method = "phone" | "email";

const schema = z
  .object({
    method: z.enum(["phone", "email"]),
    phone: z.string(),
    email: z.string(),
    password: z.string().min(1, i18n.t("validation.passwordRequired")),
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

const Login = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const { login, isAuthenticated } = useAuth();
  const [generalError, setGeneralError] = useState<string>();

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { method: "phone", phone: "", email: "", password: "" },
  });
  const method = watch("method");
  const password = watch("password");

  useEffect(() => {
    if (isAuthenticated) navigate(next, { replace: true });
  }, [isAuthenticated, navigate, next]);

  const onSubmit = async (values: FormValues) => {
    setGeneralError(undefined);
    try {
      const user = await login(
        values.method === "phone"
          ? { phone: toE164(values.phone), password: values.password }
          : { email: values.email.trim(), password: values.password },
      );
      toast.success(t("authForm.login.welcomeBack", { name: user.full_name.split(" ")[0] }));
      navigate(next, { replace: true });
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      setGeneralError(
        status === 401
          ? t("authForm.login.invalid")
          : parseApiErrors(error).general ?? t("authForm.login.failed"),
      );
    }
  };

  return (
    <AuthLayout
      title={t("authForm.login.title")}
      description={t("authForm.login.description")}
      footer={
        <>
          {t("authForm.login.noAccount")}{" "}
          <Link to={`/register${next !== "/dashboard" ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-semibold text-primary hover:underline">
            {t("authForm.login.createAccount")}
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
        <MethodToggle<Method>
          label={t("authForm.login.loginWith")}
          value={method}
          onChange={(value) => {
            setValue("method", value);
            setGeneralError(undefined);
          }}
          options={methods.map(({ labelKey, ...rest }) => ({ ...rest, label: t(labelKey) }))}
        />

        {method === "phone" ? (
          <Field label={t("authForm.phoneLabel")} htmlFor="phone" error={errors.phone?.message}>
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
                  autoFocus
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
              autoFocus
              {...errorProps("email", errors.email?.message)}
              {...register("email")}
            />
          </Field>
        )}

        <Field
          label={t("authForm.passwordLabel")}
          htmlFor="password"
          error={errors.password?.message}
          aside={
            <Link to="/forgot-password" className="text-sm font-semibold text-primary hover:underline">
              {t("authForm.login.forgot")}
            </Link>
          }
        >
          <PasswordInput
            id="password"
            autoComplete="current-password"
            value={password}
            {...errorProps("password", errors.password?.message)}
            {...register("password")}
          />
        </Field>

        <FormAlert message={generalError} />

        <Button type="submit" size="lg" className="w-full shadow-glow" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
          {t("authForm.login.submit")}
        </Button>
      </form>
    </AuthLayout>
  );
};

export default Login;
