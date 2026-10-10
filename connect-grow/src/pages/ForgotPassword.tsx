import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Loader2 } from "lucide-react";
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
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Les deux mots de passe ne correspondent pas." });

/** Réinitialisation du mot de passe par code SMS (CDC 3.1). */
const ForgotPassword = () => {
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
      setError(general ?? fields.phone ?? "L'envoi du code a échoué. Réessayez.");
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
      setError(parseApiErrors(err).general ?? "La réinitialisation a échoué. Réessayez.");
      return;
    }
    try {
      await login({ phone: toE164(phone), password: newPassword });
      toast.success("Mot de passe modifié. Vous êtes connecté.");
      navigate("/dashboard", { replace: true });
    } catch {
      toast.success("Mot de passe modifié. Connectez-vous avec le nouveau.");
      navigate("/login", { replace: true });
    } finally {
      setIsResetting(false);
    }
  });

  return (
    <AuthLayout
      title={step === "phone" ? "Mot de passe oublié" : "Choisissez un nouveau mot de passe"}
      description={
        step === "phone"
          ? "Saisissez le numéro de votre compte : nous vous enverrons un code de réinitialisation par SMS."
          : undefined
      }
      footer={
        <Link to="/login" className="font-semibold text-primary hover:underline">
          Retour à la connexion
        </Link>
      }
    >
      {step === "phone" ? (
        <form onSubmit={phoneFormState.handleSubmit(({ phone: digits }) => sendCode(digits))} noValidate className="space-y-5">
          <Field
            label="Numéro de téléphone"
            htmlFor="phone"
            error={phoneFormState.formState.errors.phone?.message}
            hint="Compte créé avec une adresse e-mail uniquement ? Ajoutez d'abord un numéro depuis votre profil, ou contactez le support."
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
            Recevoir le code
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
            if (!(await sendCode(phone))) throw new Error("Échec du renvoi");
          }}
          onChangeNumber={() => setStep("phone")}
          isSubmitting={isResetting}
          error={error}
          submitLabel="Changer mon mot de passe"
          autoSubmit={false}
        >
          <Field label="Nouveau mot de passe" htmlFor="password" error={pwdForm.formState.errors.password?.message}>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              showStrength
              value={password}
              {...errorProps("password", pwdForm.formState.errors.password?.message)}
              {...pwdForm.register("password")}
            />
          </Field>
          <Field label="Confirmer le mot de passe" htmlFor="confirm" error={pwdForm.formState.errors.confirm?.message}>
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
