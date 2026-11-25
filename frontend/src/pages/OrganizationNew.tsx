import { useId, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Check, Info, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { OrganizationType } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { AccountShell } from "@/components/layout/AccountShell";
import { PageHeader } from "@/components/common";
import { CategoryPicker } from "@/components/common/CategoryPicker";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { ImageField } from "@/components/common/ImageField";
import { errorProps, Field, fieldInputClass, FormAlert } from "@/components/auth/FormFields";
import { useAuth } from "@/contexts/AuthContext";
import { useCities } from "@/hooks/use-marketplace";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useCreateOrganization, useOrganizationLimits } from "@/hooks/use-organizations";
import { describeApiError, getApiErrorCode } from "@/lib/api-errors";
import {
  buildOrganizationBody,
  FALLBACK_LIMITS,
  NIF_MAX_LENGTH,
  ORG_TYPES,
  organizationSchema,
  toOrganizationInput,
  type OrganizationFormValues,
} from "@/lib/organization-form";
import { cn } from "@/lib/utils";
import { parseApiErrors } from "@/lib/validation";

/** Choix du type d'organisation : groupe radio avec navigation aux flèches (une seule tabulation pour le groupe). */
function TypeChoice({ value, onChange, error }: { value: OrganizationType | ""; onChange: (value: OrganizationType) => void; error?: string }) {
  const { t } = useTranslation();
  const legendId = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (from: number, delta: number) => {
    const next = (from + delta + ORG_TYPES.length) % ORG_TYPES.length;
    onChange(ORG_TYPES[next].value);
    refs.current[next]?.focus();
  };

  return (
    <fieldset>
      <legend id={legendId} className="mb-2 text-sm font-semibold">
        {t("orgNew.type")}
      </legend>
      <div role="radiogroup" aria-labelledby={legendId} aria-describedby={error ? "org-type-error" : undefined} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {ORG_TYPES.map(({ value: type, icon: Icon }, index) => {
          const selected = value === type;
          const focusable = selected || (!value && index === 0);
          return (
            <button
              key={type}
              ref={(node) => {
                refs.current[index] = node;
              }}
              type="button"
              role="radio"
              aria-checked={selected}
              tabIndex={focusable ? 0 : -1}
              onClick={() => onChange(type)}
              onKeyDown={(event) => {
                if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                  event.preventDefault();
                  move(index, 1);
                } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                  event.preventDefault();
                  move(index, -1);
                }
              }}
              className={cn(
                "relative flex min-h-[4.5rem] flex-col items-start gap-2 rounded-xl border-2 p-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                selected ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/40",
              )}
            >
              <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg", selected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <span>
                <span className="block text-sm font-bold">{t(`orgType.${type}`)}</span>
                <span className="block text-xs text-muted-foreground">{t(`orgType.${type}_desc`)}</span>
              </span>
              {selected && <Check className="absolute right-3 top-3 h-4 w-4 text-primary" aria-hidden />}
            </button>
          );
        })}
      </div>
      {error && (
        <p id="org-type-error" role="alert" className="mt-2 text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </fieldset>
  );
}

const OrganizationNew = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const online = useOnlineStatus();
  const { data: cities = [] } = useCities();
  const { data: limitsData } = useOrganizationLimits();
  const limits = limitsData ?? FALLBACK_LIMITS;
  const create = useCreateOrganization();
  const [logo, setLogo] = useState<{ file: File; preview: string } | null>(null);
  const [formError, setFormError] = useState<string>();
  const [errorCode, setErrorCode] = useState<string>();
  const categoriesLabelId = useId();

  const schema = useMemo(() => organizationSchema(limits, t, { requireType: true }), [limits, t]);
  const form = useForm<OrganizationFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { org_type: "", name: "", description: "", commune_id: "", nif: "", category_ids: [] },
  });
  const { errors } = form.formState;
  const description = form.watch("description");

  // Garde-fou : le serveur exige un numéro de connexion vérifié. Champ inconnu du front : le formulaire s'affiche
  // et le 403 `phone_verification_required` est traité à l'envoi.
  const phoneUnverified = user?.phone_verified === false;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(undefined);
    setErrorCode(undefined);
    if (!online || create.isPending) return;
    const body = buildOrganizationBody(toOrganizationInput(values, cities), { logo: logo?.file });
    try {
      const organization = await create.mutateAsync(body);
      toast.success(t("orgNew.created"));
      // Pas de bascule automatique de profil (D4) : un seul bouton « Agir sous ce profil » le propose
      navigate(`/organizations/${organization.id}`, { state: { justCreated: true }, replace: true });
    } catch (error) {
      const code = getApiErrorCode(error);
      if (code) {
        setErrorCode(code);
        setFormError(describeApiError(error));
        return;
      }
      const { fields, general } = parseApiErrors(error);
      const mapped: [keyof OrganizationFormValues, string | undefined][] = [
        ["name", fields.name],
        ["org_type", fields.org_type],
        ["description", fields.description],
        ["nif", fields.nif],
        ["category_ids", fields.category_ids],
        ["commune_id", fields.commune_id ?? fields.city_id],
      ];
      let first = true;
      for (const [field, message] of mapped) {
        if (!message) continue;
        form.setError(field, { message }, { shouldFocus: first });
        first = false;
      }
      setFormError(general ?? fields.logo ?? (first ? describeApiError(error) : undefined));
    }
  });

  return (
    <AccountShell className="max-w-2xl">
      <PageHeader title={t("orgNew.title")} description={t("orgNew.description")} />

      {phoneUnverified ? (
        <Alert>
          <Info className="h-4 w-4" aria-hidden />
          <AlertTitle>{t("orgNew.phoneRequiredTitle")}</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>{t("orgNew.phoneRequiredBody")}</p>
            <Button asChild>
              <Link to="/settings?tab=contact">{t("orgNew.phoneRequiredAction")}</Link>
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <form onSubmit={onSubmit} noValidate className="space-y-6">
          <Controller control={form.control} name="org_type" render={({ field }) => <TypeChoice value={field.value} onChange={field.onChange} error={errors.org_type?.message} />} />

          <Field label={t("orgNew.name")} htmlFor="org-name" error={errors.name?.message} hint={t("orgNew.nameHint")}>
            <Input id="org-name" autoComplete="organization" className={fieldInputClass} {...errorProps("org-name", errors.name?.message)} {...form.register("name")} />
          </Field>

          <Field
            label={t("orgNew.descriptionLabel")}
            htmlFor="org-description"
            error={errors.description?.message}
            aside={
              <span className="text-xs tabular-nums text-muted-foreground">
                {description.length}/{limits.description_max_length}
              </span>
            }
          >
            <Textarea id="org-description" className="min-h-[110px] rounded-xl bg-card" {...errorProps("org-description", errors.description?.message)} {...form.register("description")} />
          </Field>

          <div className="space-y-2">
            <p id={categoriesLabelId} className="text-sm font-semibold">
              {t("orgNew.categories")}
            </p>
            <Controller
              control={form.control}
              name="category_ids"
              render={({ field }) => (
                <CategoryPicker value={field.value} onChange={field.onChange} max={limits.max_categories_per_context} labelledBy={categoriesLabelId} />
              )}
            />
            {errors.category_ids?.message && (
              <p role="alert" className="text-sm font-medium text-destructive">
                {errors.category_ids.message}
              </p>
            )}
          </div>

          <Field label={t("orgNew.commune")} htmlFor="org-commune" error={errors.commune_id?.message} hint={t("orgNew.communeHint")}>
            <Controller
              control={form.control}
              name="commune_id"
              render={({ field }) => (
                <CommuneSelect
                  id="org-commune"
                  value={field.value}
                  onChange={field.onChange}
                  allowAll={false}
                  placeholder={t("orgNew.communePlaceholder")}
                  className="h-12 rounded-xl bg-card"
                />
              )}
            />
          </Field>

          <Field label={t("orgNew.nif")} htmlFor="org-nif" error={errors.nif?.message} hint={t("orgNew.nifHint")}>
            <Input id="org-nif" maxLength={NIF_MAX_LENGTH + 10} autoComplete="off" className={fieldInputClass} {...errorProps("org-nif", errors.nif?.message)} {...form.register("nif")} />
          </Field>

          <ImageField
            label={t("orgNew.logo")}
            src={logo?.preview}
            name={form.watch("name")}
            shape="square"
            onSelect={(file, preview) => setLogo({ file, preview })}
          />

          <FormAlert message={formError} />
          {errorCode === "organization_limit_reached" && (
            <Button asChild variant="outline">
              <Link to="/profiles">{t("orgNew.limitLink")}</Link>
            </Button>
          )}
          {errorCode === "phone_verification_required" && (
            <Button asChild variant="outline">
              <Link to="/settings?tab=contact">{t("orgNew.phoneRequiredAction")}</Link>
            </Button>
          )}
          {!online && <p className="text-sm text-muted-foreground">{t("orgNew.offlineDraft")} {t("common.offlineAction")}</p>}

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center">
            <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
              {t("orgNew.cancel")}
            </Button>
            <Button type="submit" size="lg" className="w-full sm:w-auto" disabled={create.isPending || !online}>
              {create.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t("orgNew.submit")}
            </Button>
          </div>
        </form>
      )}
    </AccountShell>
  );
};

export default OrganizationNew;
