import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";
import { toast } from "sonner";
import apiClient from "@/api/client";
import { Button } from "@/components/ui/button";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { errorProps, Field, FormAlert, PasswordInput, PhoneInput } from "@/components/auth/FormFields";
import { OTP_LENGTH, OtpStep } from "@/components/auth/OtpStep";
import { useAuth } from "@/contexts/AuthContext";
import { useRequestOtp } from "@/hooks/use-otp";
import { localPhoneSchema, parseApiErrors, passwordSchema, toE164 } from "@/lib/validation";

const phoneForm = z.object({ phone: localPhoneSchema });

const passwordForm = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: i18n.t("validation.passwordMismatch") });

/** Réinitialisation du mot de passe par code SMS (CDC 3.1). */
const ForgotPassword = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { login } = useAuth();
  const requestOtp = useRequestOtp();
  const [step, setStep] = useState<"phone" | "reset">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const [isResetting, setIsResetting] = useState(false);

  const phoneFormState = useForm<z.infer<typeof phoneForm>>({ resolver: zodResolver(phoneForm), defaultValues: { phone: "" } });
  const pwdForm = useForm<z.infer<typeof passwordForm>>({ resolver: zodResolver(passwordForm), defaultValues: { password: "", confirm: "" } });
  const [password, confirm] = pwdForm.watch(["password", "confirm"]);

  /** Envoie le code ; renvoie false (erreur affichée) si l'envoi échoue. */
  const sendCode = async (digits: string) => {
    setError(undefined);
    try {
      await requestOtp.mutateAsync({ phone: toE164(digits), purpose: "PASSWORD_RESET" });
      setPhone(digits);
      setCode("");
      setStep("reset");
      return true;
    } catch (err) {
      const { general, fields } = parseApiErrors(err);
      setError(general ?? fields.phone ?? t("authForm.register.sendFailed"));
      return false;
    }
  };

  const resetPassword = pwdForm.handleSubmit(async ({ password: newPassword }) => {
    if (code.length < OTP_LENGTH) return;
    setError(undefined);
    setIsResetting(true);
    try {
      await apiClient.post("accounts/password-reset/confirm/", { phone: toE164(phone), code, new_password: newPassword });
    } catch (err) {
      setIsResetting(false);
      setError(parseApiErrors(err).general ?? t("authForm.forgot.failed"));
      return;
    }
    try {
      await login({ phone: toE164(phone), password: newPassword });
      toast.success(t("authForm.forgot.doneLoggedIn"));
      navigate("/dashboard", { replace: true });
    } catch {
      toast.success(t("authForm.forgot.doneLogin"));
      navigate("/login", { replace: true });
    } finally {
      setIsResetting(false);
    }
  });

  return (
    <AuthLayout
      title={step === "phone" ? t("authForm.forgot.title") : t("authForm.forgot.newTitle")}
      description={
        step === "phone" ? t("authForm.forgot.description") : undefined
      }
      footer={
        <Link to="/login" className="font-semibold text-primary hover:underline">
          {t("authForm.forgot.backToLogin")}
        </Link>
      }
    >
      {step === "phone" ? (
        <form onSubmit={phoneFormState.handleSubmit(({ phone: digits }) => sendCode(digits))} noValidate className="space-y-5">
          <Field
            label={t("authForm.phoneLabel")}
            htmlFor="phone"
            error={phoneFormState.formState.errors.phone?.message}
            hint={t("authForm.forgot.emailOnlyHint")}
          >
            <Controller
              control={phoneFormState.control}
              name="phone"
              render={({ field }) => (
                <PhoneInput
                  id="phone"
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  autoFocus
                  invalid={!!phoneFormState.formState.errors.phone}
                  {...errorProps("phone", phoneFormState.formState.errors.phone?.message)}
                />
              )}
            />
          </Field>
          <FormAlert message={error} />
          <Button type="submit" size="lg" className="w-full" disabled={requestOtp.isPending}>
            {requestOtp.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <KeyRound aria-hidden />}
            {t("authForm.forgot.receiveCode")}
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
          onSubmit={resetPassword}
          onResend={async () => {
            if (!(await sendCode(phone))) throw new Error(t("authForm.forgot.resendFailed"));
          }}
          onChangeNumber={() => setStep("phone")}
          isSubmitting={isResetting}
          error={error}
          submitLabel={t("authForm.forgot.submit")}
          autoSubmit={false}
        >
          <Field label={t("authForm.newPassword")} htmlFor="password" error={pwdForm.formState.errors.password?.message}>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              showStrength
              value={password}
              {...errorProps("password", pwdForm.formState.errors.password?.message)}
              {...pwdForm.register("password")}
            />
          </Field>
          <Field label={t("authForm.confirmPassword")} htmlFor="confirm" error={pwdForm.formState.errors.confirm?.message}>
            <PasswordInput
              id="confirm"
              autoComplete="new-password"
              value={confirm}
              {...errorProps("confirm", pwdForm.formState.errors.confirm?.message)}
              {...pwdForm.register("confirm")}
            />
          </Field>
        </OtpStep>
      )}
    </AuthLayout>
  );
};

export default ForgotPassword;
