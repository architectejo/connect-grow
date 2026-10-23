import { useEffect, useId, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2, Lock, Save } from "lucide-react";
import { toast } from "sonner";
import type { OrganizationInternal } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { AccessDenied, PageHeader } from "@/components/common";
import { CategoryPicker } from "@/components/common/CategoryPicker";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { ImageField } from "@/components/common/ImageField";
import { errorProps, Field, fieldInputClass, FormAlert } from "@/components/auth/FormFields";
import { OrganizationPage } from "@/components/organizations/OrganizationPage";
import { useCities } from "@/hooks/use-marketplace";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useOrganizationLimits, useUpdateOrganization } from "@/hooks/use-organizations";
import { describeApiError, getApiErrorCode } from "@/lib/api-errors";
import {
  buildOrganizationBody,
  diffOrganizationInput,
  FALLBACK_LIMITS,
  lockedFields,
  NIF_MAX_LENGTH,
  organizationSchema,
  toOrganizationInput,
  type OrganizationFormValues,
} from "@/lib/organization-form";
import { parseApiErrors } from "@/lib/validation";

const valuesOf = (org: OrganizationInternal): OrganizationFormValues => ({
  org_type: org.org_type,
  name: org.name,
  description: org.description,
  commune_id: org.commune_id ?? "",
  nif: org.nif ?? "",
  category_ids: org.category_ids,
});

function EditForm({ org }: { org: OrganizationInternal }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const { data: cities = [] } = useCities();
  const { data: limitsData } = useOrganizationLimits();
  const limits = limitsData ?? FALLBACK_LIMITS;
  const update = useUpdateOrganization(org.id);
  const locks = lockedFields(org);
  const [logo, setLogo] = useState<{ file: File; preview: string } | null>(null);
  const [removeLogo, setRemoveLogo] = useState(false);
  const [formError, setFormError] = useState<string>();
  const [leaveOpen, setLeaveOpen] = useState(false);
  const categoriesLabelId = useId();

  const schema = useMemo(() => organizationSchema(limits, t, { requireType: false }), [limits, t]);
  const form = useForm<OrganizationFormValues>({ resolver: zodResolver(schema), defaultValues: valuesOf(org) });
  const { errors, isDirty } = form.formState;
  const description = form.watch("description");
  const dirty = isDirty || !!logo || removeLogo;

  // Modifications non enregistrées : l'avertissement du navigateur couvre la fermeture de l'onglet et le rechargement
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const lockedText = locks.name === "validated" ? t("orgEdit.nameLocked") : t("orgEdit.nameLockedPending");

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(undefined);
    if (!online || update.isPending) return;
    const changes = diffOrganizationInput(org, toOrganizationInput(values, cities));
    // Un champ verrouillé n'est jamais envoyé : le serveur resterait de toute façon la référence (409)
    if (locks.name) delete changes.name;
    if (locks.nif) delete changes.nif;
    if (Object.keys(changes).length === 0 && !logo && !removeLogo) return;
    try {
      const saved = await update.mutateAsync(buildOrganizationBody(changes, { logo: logo?.file, removeLogo }));
      form.reset(valuesOf(saved));
      setLogo(null);
      setRemoveLogo(false);
      toast.success(t("orgEdit.saved"));
    } catch (error) {
      const code = getApiErrorCode(error);
      if (code === "name_locked_by_verification") {
        // Le serveur fait foi : le nom est remis à sa valeur d'origine
        form.setValue("name", org.name, { shouldDirty: false });
        form.setError("name", { message: t("errors.code.name_locked_by_verification") }, { shouldFocus: true });
        return;
      }
      if (code === "nif_locked_by_verification") {
        form.setValue("nif", org.nif ?? "", { shouldDirty: false });
        form.setError("nif", { message: t("errors.code.nif_locked_by_verification") }, { shouldFocus: true });
        return;
      }
      if (code) {
        setFormError(describeApiError(error, { inOrganization: true }));
        return;
      }
      const { fields, general } = parseApiErrors(error);
      let first = true;
      const mapped: [keyof OrganizationFormValues, string | undefined][] = [
        ["name", fields.name],
        ["description", fields.description],
        ["nif", fields.nif],
        ["category_ids", fields.category_ids],
        ["commune_id", fields.commune_id ?? fields.city_id],
      ];
      for (const [field, message] of mapped) {
        if (!message) continue;
        form.setError(field, { message }, { shouldFocus: first });
        first = false;
      }
      setFormError(general ?? fields.logo ?? fields.org_type ?? (first ? describeApiError(error, { inOrganization: true }) : undefined));
    }
  });

  const back = () => (dirty ? setLeaveOpen(true) : navigate(`/organizations/${org.id}`));

  return (
    <>
      <PageHeader title={t("orgEdit.title")} description={t("orgEdit.description")} />
      <form onSubmit={onSubmit} noValidate className="max-w-2xl space-y-6">
        <div>
          <p className="mb-1.5 text-sm font-semibold">{t("orgEdit.typeLabel")}</p>
          <Badge variant="secondary">{t(`orgType.${org.org_type}`)}</Badge>
          <p className="mt-1.5 text-xs text-muted-foreground">{t("orgEdit.typeFixed")}</p>
        </div>

        <Field label={t("orgNew.name")} htmlFor="org-name" error={errors.name?.message} hint={locks.name ? lockedText : t("orgNew.nameHint")}>
          <Input
            id="org-name"
            readOnly={!!locks.name}
            autoComplete="organization"
            className={fieldInputClass}
            {...errorProps("org-name", errors.name?.message)}
            {...form.register("name")}
          />
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
            render={({ field }) => <CategoryPicker value={field.value} onChange={field.onChange} max={limits.max_categories_per_context} labelledBy={categoriesLabelId} />}
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
              <CommuneSelect id="org-commune" value={field.value} onChange={field.onChange} allowAll={false} placeholder={t("orgNew.communePlaceholder")} className="h-12 rounded-xl bg-card" />
            )}
          />
        </Field>

        <Field label={t("orgNew.nif")} htmlFor="org-nif" error={errors.nif?.message} hint={locks.nif ? t("orgEdit.nifLocked") : t("orgNew.nifHint")}>
          <Input
            id="org-nif"
            readOnly={locks.nif}
            maxLength={NIF_MAX_LENGTH + 10}
            autoComplete="off"
            className={fieldInputClass}
            {...errorProps("org-nif", errors.nif?.message)}
            {...form.register("nif")}
          />
        </Field>

        <ImageField
          label={t("imageField.changeLogo")}
          src={removeLogo ? null : (logo?.preview ?? org.logo)}
          name={org.name}
          shape="square"
          onSelect={(file, preview) => {
            setLogo({ file, preview });
            setRemoveLogo(false);
          }}
          extra={
            (org.logo || logo) && !removeLogo ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setLogo(null);
                  // Retirer un logo qui n'existe pas encore sur le serveur ne demande aucun envoi
                  setRemoveLogo(!!org.logo);
                }}
              >
                {t("orgEdit.removeLogo")}
              </Button>
            ) : null
          }
        />

        <FormAlert message={formError} />
        {!online && <p className="text-sm text-muted-foreground">{t("common.offlineAction")}</p>}

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center">
          <Button type="button" variant="ghost" onClick={back}>
            {t("common.back")}
          </Button>
          <Button type="submit" size="lg" className="w-full sm:w-auto" disabled={update.isPending || !online || !dirty}>
            {update.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
            {t("orgEdit.save")}
          </Button>
        </div>
      </form>

      <AlertDialog open={leaveOpen} onOpenChange={setLeaveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("orgEdit.unsavedTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("orgEdit.unsavedBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("orgEdit.unsavedStay")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => navigate(`/organizations/${org.id}`)}>{t("orgEdit.unsavedLeave")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

const OrganizationEdit = () => {
  const { t } = useTranslation();
  return (
    <OrganizationPage section="profile">
      {(org) =>
        org.capabilities.includes("org.edit_profile") ? (
          <EditForm key={org.id} org={org} />
        ) : (
          <AccessDenied
            title={t("orgEdit.title")}
            description={t("orgEdit.readOnly")}
            action={
              <Button asChild variant="outline">
                <Link to={`/organizations/${org.id}`}>
                  <Lock aria-hidden /> {t("common.back")}
                </Link>
              </Button>
            }
          />
        )
      }
    </OrganizationPage>
  );
};

export default OrganizationEdit;
