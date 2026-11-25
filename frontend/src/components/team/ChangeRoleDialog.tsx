import { useRef, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { OrganizationMember, OrganizationRole, Uuid } from "@/api/types";
import { FormAlert } from "@/components/auth/FormFields";
import { ResponsiveDialog } from "@/components/common/ResponsiveDialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useChangeMemberRole } from "@/hooks/use-organization-team";
import { assignableRoles, classifyTeamError, isSensitiveConfirmComplete, needsReauthentication, type SensitiveConfirmValue } from "@/lib/team";
import { cn } from "@/lib/utils";
import { SensitiveConfirmFields } from "./SensitiveConfirmFields";
import { useRateBlock } from "./use-rate-block";

interface ChangeRoleDialogProps {
  orgId: Uuid;
  member: OrganizationMember;
  actorRole: OrganizationRole;
  online: boolean;
  onClose: () => void;
  /** Texte annoncé aux lecteurs d'écran (région `aria-live` de la page). */
  onAnnounce: (message: string) => void;
}

const EMPTY: SensitiveConfirmValue = { confirmed: false, password: "" };

/**
 * E6b : changer le rôle d'un membre. Étape 2 (case et mot de passe) seulement pour une promotion vers Propriétaire
 * ou la rétrogradation d'un Propriétaire. Un mot de passe inutile n'est jamais envoyé.
 */
export function ChangeRoleDialog({ orgId, member, actorRole, online, onClose, onAnnounce }: ChangeRoleDialogProps) {
  const { t } = useTranslation();
  const mutation = useChangeMemberRole(orgId);
  const [role, setRole] = useState<OrganizationRole>(member.role);
  const [step, setStep] = useState<1 | 2>(1);
  const [secret, setSecret] = useState<SensitiveConfirmValue>(EMPTY);
  const [formError, setFormError] = useState<string>();
  const [roleError, setRoleError] = useState<string>();
  const [passwordError, setPasswordError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const passwordRef = useRef<HTMLInputElement>(null);
  const strong = needsReauthentication(member.role, role);
  const pending = mutation.isPending;

  const clearErrors = () => {
    setFormError(undefined);
    setRoleError(undefined);
    setPasswordError(undefined);
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (pending || blocked || !online || role === member.role) return;
    if (strong && step === 1) {
      clearErrors();
      setStep(2);
      return;
    }
    if (strong && !isSensitiveConfirmComplete(secret)) return;
    clearErrors();
    try {
      const body = strong ? { role, confirm: true as const, password: secret.password } : { role };
      const updated = await mutation.mutateAsync({ membershipId: member.membership_id, body });
      setSecret(EMPTY);
      if (updated.role !== member.role) {
        const message = t("team.roleChanged", { name: member.display_name, role: t(`role.${updated.role}`) });
        toast.success(message);
        onAnnounce(message);
      }
      onClose();
    } catch (error) {
      // Quel que soit l'échec (réseau, 5xx, champ, limiteur, mauvais mot de passe) : le mot de passe quitte le champ et la mutation
      mutation.reset();
      setSecret((current) => ({ ...current, password: "" }));
      const failure = classifyTeamError(error);
      switch (failure.kind) {
        case "reauth":
          setPasswordError(failure.message);
          requestAnimationFrame(() => passwordRef.current?.focus());
          break;
        case "gone":
          toast.info(failure.message);
          onClose();
          break;
        case "denied":
          toast.error(failure.message);
          onClose();
          break;
        case "rate":
          setFormError(failure.message);
          block(failure.retryAfter);
          break;
        case "field":
          setStep(1);
          setRoleError(failure.message);
          break;
        default:
          setFormError(failure.message);
      }
    }
  };

  const roles = assignableRoles(actorRole);
  const offlineId = "change-role-offline";
  const submitDisabled = pending || blocked || !online || (step === 1 ? role === member.role : !isSensitiveConfirmComplete(secret));

  return (
    <ResponsiveDialog open onOpenChange={(next) => !next && !pending && onClose()} title={t("team.changeRoleTitle", { name: member.display_name })}>
      <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
        {step === 1 ? (
          <div className="space-y-2">
            <RadioGroup
              value={role}
              onValueChange={(next) => {
                setRole(next as OrganizationRole);
                setRoleError(undefined);
                setSecret(EMPTY);
              }}
              disabled={pending}
              aria-label={t("team.roleGroup")}
              aria-describedby={roleError ? "change-role-error" : undefined}
              aria-invalid={!!roleError || undefined}
            >
              {roles.map((option) => {
                const id = `change-role-${option}`;
                return (
                  <div key={option} className={cn("flex min-h-11 items-start gap-3 rounded-xl border p-3", option === role && "border-primary bg-primary/5")}>
                    <RadioGroupItem id={id} value={option} autoFocus={option === role} className="mt-0.5" />
                    <Label htmlFor={id} className="flex-1 cursor-pointer space-y-0.5 text-sm">
                      <span className="block font-semibold">
                        {t(`role.${option}`)}
                        {option === member.role && <span className="ml-1 font-normal text-muted-foreground">{t("team.currentRole")}</span>}
                      </span>
                      <span className="block font-normal text-muted-foreground">{t(`role.${option}_desc`)}</span>
                    </Label>
                  </div>
                );
              })}
            </RadioGroup>
            {roleError && (
              <p id="change-role-error" role="alert" className="text-sm font-medium text-destructive">
                {roleError}
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm">{t(role === "OWNER" ? "team.promoteOwnerBody" : "team.demoteOwnerBody", { name: member.display_name })}</p>
            <SensitiveConfirmFields
              idPrefix="change-role"
              value={secret}
              onChange={(next) => {
                setSecret(next);
                setPasswordError(undefined);
              }}
              confirmLabel={t("team.confirmChange")}
              error={passwordError}
              disabled={pending}
              passwordRef={passwordRef}
            />
          </div>
        )}

        <FormAlert message={formError} />
        {!online && (
          <p id={offlineId} className="text-xs text-muted-foreground">
            {t("common.offlineAction")}
          </p>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          {step === 2 ? (
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={pending}
              onClick={() => {
                clearErrors();
                setSecret(EMPTY);
                setStep(1);
              }}
            >
              {t("team.back")}
            </Button>
          ) : (
            <Button type="button" variant="outline" className="min-h-11" disabled={pending} onClick={onClose}>
              {t("common.cancel")}
            </Button>
          )}
          <Button type="submit" className="min-h-11" disabled={submitDisabled} aria-describedby={!online ? offlineId : undefined}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {step === 2 ? t("team.confirmRoleButton") : t("team.saveRole")}
          </Button>
        </div>
      </form>
    </ResponsiveDialog>
  );
}
