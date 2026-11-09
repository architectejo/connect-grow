import { useRef, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { OrganizationMember, TransferNewRole, Uuid } from "@/api/types";
import { FormAlert } from "@/components/auth/FormFields";
import { ResponsiveDialog } from "@/components/common/ResponsiveDialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useTransferOwnership } from "@/hooks/use-organization-team";
import { classifyTeamError, isSensitiveConfirmComplete, type SensitiveConfirmValue } from "@/lib/team";
import { cn } from "@/lib/utils";
import { SensitiveConfirmFields } from "./SensitiveConfirmFields";
import { useRateBlock } from "./use-rate-block";

/** Rôles que l'acteur peut garder après le transfert : jamais Propriétaire (contrat §1.4). */
const MY_NEW_ROLES: TransferNewRole[] = ["ADMIN", "EDITOR", "ANALYST"];
const EMPTY: SensitiveConfirmValue = { confirmed: false, password: "" };

interface TransferOwnershipDialogProps {
  orgId: Uuid;
  target: OrganizationMember;
  online: boolean;
  onClose: () => void;
  onAnnounce: (message: string) => void;
}

/** E6c : transfert de propriété. Case de confirmation et mot de passe obligatoires ; focus initial sur « Annuler ». */
export function TransferOwnershipDialog({ orgId, target, online, onClose, onAnnounce }: TransferOwnershipDialogProps) {
  const { t } = useTranslation();
  const mutation = useTransferOwnership(orgId);
  const [myRole, setMyRole] = useState<TransferNewRole>("ADMIN");
  const [secret, setSecret] = useState<SensitiveConfirmValue>(EMPTY);
  const [formError, setFormError] = useState<string>();
  const [roleError, setRoleError] = useState<string>();
  const [passwordError, setPasswordError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const passwordRef = useRef<HTMLInputElement>(null);
  const pending = mutation.isPending;

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (pending || blocked || !online || !isSensitiveConfirmComplete(secret)) return;
    setFormError(undefined);
    setRoleError(undefined);
    setPasswordError(undefined);
    try {
      await mutation.mutateAsync({ membership_id: target.membership_id, my_new_role: myRole, confirm: true, password: secret.password });
      setSecret(EMPTY);
      const message = t("team.transferred", { name: target.display_name });
      toast.success(message);
      onAnnounce(message);
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
          setRoleError(failure.message);
          break;
        default:
          setFormError(failure.message);
      }
    }
  };

  const offlineId = "transfer-offline";
  return (
    <ResponsiveDialog open onOpenChange={(next) => !next && !pending && onClose()} title={t("team.transferTitle", { name: target.display_name })}>
      <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
        <p className="text-sm">{t("team.transferBody", { name: target.display_name })}</p>

        <div className="space-y-2">
          <p id="transfer-my-role" className="text-sm font-semibold">
            {t("team.transferMyRole")}
          </p>
          <RadioGroup
            value={myRole}
            onValueChange={(next) => {
              setMyRole(next as TransferNewRole);
              setRoleError(undefined);
            }}
            disabled={pending}
            aria-labelledby="transfer-my-role"
            aria-describedby={roleError ? "transfer-role-error" : undefined}
            aria-invalid={!!roleError || undefined}
          >
            {MY_NEW_ROLES.map((option) => {
              const id = `transfer-role-${option}`;
              return (
                <div key={option} className={cn("flex min-h-11 items-start gap-3 rounded-xl border p-3", option === myRole && "border-primary bg-primary/5")}>
                  <RadioGroupItem id={id} value={option} className="mt-0.5" />
                  <Label htmlFor={id} className="flex-1 cursor-pointer space-y-0.5 text-sm">
                    <span className="block font-semibold">{t(`role.${option}`)}</span>
                    <span className="block font-normal text-muted-foreground">{t(`role.${option}_desc`)}</span>
                  </Label>
                </div>
              );
            })}
          </RadioGroup>
          {roleError && (
            <p id="transfer-role-error" role="alert" className="text-sm font-medium text-destructive">
              {roleError}
            </p>
          )}
        </div>

        <p className="text-xs text-muted-foreground">{t("team.transferAlt", { name: target.display_name })}</p>

        <SensitiveConfirmFields
          idPrefix="transfer"
          value={secret}
          onChange={(next) => {
            setSecret(next);
            setPasswordError(undefined);
          }}
          confirmLabel={t("team.transferConfirm")}
          error={passwordError}
          disabled={pending}
          passwordRef={passwordRef}
        />

        <FormAlert message={formError} />
        {!online && (
          <p id={offlineId} className="text-xs text-muted-foreground">
            {t("common.offlineAction")}
          </p>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" className="min-h-11" autoFocus disabled={pending} onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            variant="destructive"
            className="min-h-11"
            disabled={pending || blocked || !online || !isSensitiveConfirmComplete(secret)}
            aria-describedby={!online ? offlineId : undefined}
          >
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("team.transferButton")}
          </Button>
        </div>
      </form>
    </ResponsiveDialog>
  );
}
