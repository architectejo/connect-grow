import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { ProviderProfile, Uuid } from "@/api/types";
import { errorProps, Field, fieldInputClass, FormAlert } from "@/components/auth/FormFields";
import { CategoryPicker } from "@/components/common/CategoryPicker";
import { ResponsiveDialog } from "@/components/common/ResponsiveDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { describeApiError, getApiErrorCode } from "@/lib/api-errors";
import { parseApiErrors } from "@/lib/validation";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useOrganizationLimits } from "@/hooks/use-organizations";
import { useActivateProvider, useUpdateProvider } from "@/hooks/use-provider";
import { FALLBACK_LIMITS } from "@/lib/organization-form";

const NAME_MIN = 2;
const NAME_MAX = 255;
const BIO_MAX = 2000;

interface ProviderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Profil existant : modification. Absent : activation. */
  profile?: ProviderProfile | null;
  /** Nom du compte, proposé comme nom affiché public (l'utilisateur le voit et peut le changer : règle 10). */
  accountName: string;
  /** Appelé après un succès (activation ou modification), avec le profil renvoyé par le serveur. */
  onDone?: (profile: ProviderProfile, created: boolean) => void;
}

/**
 * Activation ou modification du profil prestataire. Le nom affiché est PUBLIC : il est pré-rempli avec le nom du
 * compte mais montré à l'utilisateur avant publication (le profil personnel n'est publié que sous la forme « Marie K. »).
 */
export function ProviderDialog({ open, onOpenChange, profile, accountName, onDone }: ProviderDialogProps) {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  const editing = !!profile && profile.status === "ACTIVE";
  const nameId = useId();
  const bioId = useId();
  const categoriesId = useId();
  const { data: limits } = useOrganizationLimits();
  const maxCategories = (limits ?? FALLBACK_LIMITS).max_categories_per_context;
  const activate = useActivateProvider();
  const update = useUpdateProvider();
  const pending = activate.isPending || update.isPending;

  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [categoryIds, setCategoryIds] = useState<Uuid[]>([]);
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; bio?: string }>({});
  const [formError, setFormError] = useState<string>();

  // À chaque ouverture : valeurs du profil existant, ou nom du compte proposé pour une activation
  useEffect(() => {
    if (!open) return;
    setName(editing ? profile.display_name : accountName);
    setBio(editing ? profile.bio : "");
    setCategoryIds(editing ? profile.category_ids : []);
    setFieldErrors({});
    setFormError(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seule l'ouverture réinitialise le formulaire
  }, [open]);

  const validate = () => {
    const errors: { name?: string; bio?: string } = {};
    const trimmed = name.trim();
    if (trimmed.length < NAME_MIN) errors.name = t("provider.nameTooShort");
    else if (trimmed.length > NAME_MAX) errors.name = t("provider.nameTooLong");
    if (bio.length > BIO_MAX) errors.bio = t("provider.bioTooLong");
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(undefined);
    if (!validate() || pending || !online) return;
    const input = { display_name: name.trim(), bio: bio.trim(), category_ids: categoryIds };
    try {
      if (editing) {
        const saved = await update.mutateAsync(input);
        toast.success(t("profiles.provider.updated"));
        onDone?.(saved, false);
      } else {
        const { profile: saved, created } = await activate.mutateAsync(input);
        toast.success(t(created ? "profiles.provider.activated" : "profiles.provider.reactivated"));
        onDone?.(saved, created);
      }
      onOpenChange(false);
    } catch (error) {
      const code = getApiErrorCode(error);
      if (code) {
        // Profil désactivé : on propose de le réactiver plutôt que de répéter un refus générique
        setFormError(code === "DENY_OBJECT_STATE" ? t("provider.disabledEdit") : describeApiError(error));
        return;
      }
      const { fields, general } = parseApiErrors(error);
      setFieldErrors({ name: fields.display_name, bio: fields.bio });
      setFormError(general ?? fields.category_ids ?? (fields.display_name || fields.bio ? undefined : describeApiError(error)));
    }
  };

  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={(next) => !pending && onOpenChange(next)}
      title={t(editing ? "provider.dialogTitleEdit" : "provider.dialogTitleActivate")}
      description={t("provider.dialogDescription")}
    >
      <form onSubmit={submit} noValidate className="space-y-5">
        <Field label={t("provider.displayName")} htmlFor={nameId} error={fieldErrors.name} hint={t("provider.displayNameHint")}>
          <Input
            id={nameId}
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={NAME_MAX + 20}
            className={fieldInputClass}
            {...errorProps(nameId, fieldErrors.name)}
          />
        </Field>
        <Field label={t("provider.bio")} htmlFor={bioId} error={fieldErrors.bio} aside={<span className="text-xs tabular-nums text-muted-foreground">{bio.length}/{BIO_MAX}</span>}>
          <Textarea
            id={bioId}
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            className="min-h-[96px] rounded-xl bg-card"
            {...errorProps(bioId, fieldErrors.bio)}
          />
        </Field>
        <div className="space-y-2">
          <p id={categoriesId} className="text-sm font-semibold">
            {t("provider.categories")}
          </p>
          <CategoryPicker value={categoryIds} onChange={setCategoryIds} max={maxCategories} labelledBy={categoriesId} disabled={pending} />
        </div>
        <FormAlert message={formError} />
        {!online && <p className="text-sm text-muted-foreground">{t("common.offlineAction")}</p>}
        <Button type="submit" className="w-full" disabled={pending || !online}>
          {pending && <Loader2 className="animate-spin" aria-hidden />}
          {t(editing ? "provider.submitEdit" : "provider.submitActivate")}
        </Button>
      </form>
    </ResponsiveDialog>
  );
}
