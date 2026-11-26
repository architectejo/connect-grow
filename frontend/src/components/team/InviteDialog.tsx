import { useState, type FormEvent } from "react";
import { AlertTriangle, Info, Loader2, UserCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { InvitableRole, OrganizationRole, Uuid } from "@/api/types";
import { Field, FormAlert, errorProps, fieldInputClass } from "@/components/auth/FormFields";
import { ResponsiveDialog } from "@/components/common/ResponsiveDialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useCreateInvitation } from "@/hooks/use-organization-team";
import { useOrganizationLimits } from "@/hooks/use-organizations";
import { formatLongDate } from "@/lib/format";
import { INVITATION_LABEL_MAX, classifyCreateInvitationError } from "@/lib/invitations";
import { buildInvitationLink } from "@/lib/invitation-token";
import { invitableRoles, roleRequiresConfirmation, scopeLabel } from "@/lib/team";
import { cn } from "@/lib/utils";
import { CopyLinkField } from "./CopyLinkField";
import { useRateBlock } from "./use-rate-block";

interface InviteDialogProps {
  orgId: Uuid;
  orgName: string;
  /** Rôle de l'émetteur : les rôles proposés sont ceux qu'il peut déléguer (le serveur reste l'arbitre). */
  actorRole: OrganizationRole;
  online: boolean;
  /** `created` : un lien a été créé (l'écran passe sur l'onglet Invitations). */
  onClose: (created: boolean) => void;
  onAnnounce: (message: string) => void;
}

interface CreatedLink {
  url: string;
  role: InvitableRole;
  expiresAt: string;
  /** Invitation Administrateur : la personne devra donner son code à l'émetteur ou à un administrateur principal. */
  requiresConfirmation: boolean;
}

/**
 * E6a : inviter une personne (spec D2 §7). Étape 1 : rôle (ce que l'émetteur peut déléguer ; Administrateur avec « Confirmation
 * requise », jamais Administrateur principal), périmètre affiché (jamais choisi ni envoyé en V1) et étiquette facultative. Étape 2 : le lien, affiché UNE SEULE FOIS.
 * Le jeton ne vit que dans l'état local de ce composant (supprimé à la fermeture) : ni cache de requêtes, ni stockage,
 * ni toast, ni `aria-live`, ni journal. Aucun champ téléphone, e-mail ni identifiant : aucune recherche de compte.
 */
export function InviteDialog({ orgId, orgName, actorRole, online, onClose, onAnnounce }: InviteDialogProps) {
  const { t } = useTranslation();
  const mutation = useCreateInvitation(orgId);
  const limits = useOrganizationLimits();
  const [role, setRole] = useState<InvitableRole | "">("");
  const [label, setLabel] = useState("");
  const [link, setLink] = useState<CreatedLink | null>(null);
  const [copied, setCopied] = useState(false);
  const [formError, setFormError] = useState<string>();
  const [roleError, setRoleError] = useState<string>();
  const [labelError, setLabelError] = useState<string>();
  const [blocked, block] = useRateBlock();
  const pending = mutation.isPending;
  const ttlDays = limits.data?.invitation_ttl_days;
  const roles = invitableRoles(actorRole);

  const finish = () => {
    // Le jeton quitte l'état local et le cache de mutations
    setLink(null);
    mutation.reset();
    onClose(link !== null);
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (pending || blocked || !online || !role) return;
    setFormError(undefined);
    setRoleError(undefined);
    setLabelError(undefined);
    const trimmed = label.trim();
    try {
      const created = await mutation.mutateAsync({ role, ...(trimmed ? { label: trimmed } : {}) });
      setLink({
        url: buildInvitationLink(window.location.origin, created.link_token),
        role: created.role,
        expiresAt: created.expires_at,
        requiresConfirmation: created.requires_confirmation ?? roleRequiresConfirmation(created.role),
      });
      // Le jeton ne reste pas dans le cache de mutations : l'état local suffit à l'afficher
      mutation.reset();
    } catch (error) {
      const failure = classifyCreateInvitationError(error);
      switch (failure.kind) {
        case "denied":
          toast.error(failure.message);
          onClose(false);
          break;
        case "rate":
          setFormError(failure.message);
          block(failure.retryAfter);
          break;
        case "field":
          if (failure.field === "label") setLabelError(failure.message);
          else setRoleError(failure.message);
          break;
        default:
          // Réseau coupé compris : valeurs conservées, aucune relance automatique
          setFormError(failure.message);
      }
    }
  };

  if (link) {
    const roleName = t(`role.${link.role}`);
    const date = formatLongDate(link.expiresAt);
    return (
      <ResponsiveDialog open dismissible={false} onOpenChange={(next) => !next && finish()} title={t("team.invite.linkTitle")}>
        <div className="space-y-4">
          <Alert role="alert">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            <AlertDescription>{link.requiresConfirmation ? t("team.invite.linkWarningAdmin") : t("team.invite.linkWarning", { role: roleName })}</AlertDescription>
          </Alert>
          <CopyLinkField
            value={link.url}
            shareTitle={t("team.invite.shareTitle")}
            shareText={t("team.invite.shareText", { org: orgName, date })}
            onCopied={() => setCopied(true)}
            onAnnounce={onAnnounce}
          />
          <p className="text-sm text-muted-foreground">{t("team.invite.summary", { role: roleName, date })}</p>
          <div className="space-y-2">
            <Button type="button" variant="outline" className="min-h-11 w-full" onClick={finish}>
              {t("team.invite.done")}
            </Button>
            {!copied && <p className="text-center text-xs text-muted-foreground">{t("team.invite.notCopied")}</p>}
          </div>
        </div>
      </ResponsiveDialog>
    );
  }

  const offlineId = "invite-offline";
  const labelId = "invite-label";
  const counterId = "invite-label-count";
  return (
    <ResponsiveDialog open onOpenChange={(next) => !next && !pending && onClose(false)} title={t("team.invite.title")}>
      <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
        <p className="text-sm">{t("team.invite.intro")}</p>

        <div className="space-y-2">
          <p id="invite-role-label" className="text-sm font-semibold">
            {t("team.invite.roleLabel")}
          </p>
          <RadioGroup
            value={role}
            onValueChange={(next) => {
              setRole(next as InvitableRole);
              setRoleError(undefined);
            }}
            disabled={pending}
            aria-labelledby="invite-role-label"
            aria-describedby={roleError ? "invite-role-error" : undefined}
            aria-invalid={!!roleError || undefined}
          >
            {roles.map((option, index) => {
              const id = `invite-role-${option}`;
              const confirmation = roleRequiresConfirmation(option);
              return (
                <div key={option} className={cn("flex min-h-11 items-start gap-3 rounded-xl border p-3", option === role && "border-primary bg-primary/5")}>
                  <RadioGroupItem id={id} value={option} autoFocus={index === 0} className="mt-0.5" />
                  <Label htmlFor={id} className="flex-1 cursor-pointer space-y-0.5 text-sm">
                    <span className="flex flex-wrap items-center gap-2 font-semibold">
                      {t(`role.${option}`)}
                      {confirmation && (
                        <Badge variant="outline" className="gap-1 font-medium">
                          <UserCheck className="h-3.5 w-3.5" aria-hidden />
                          {t("team.invite.confirmBadge")}
                        </Badge>
                      )}
                    </span>
                    <span className="block font-normal text-muted-foreground">{t(`role.${option}_desc`)}</span>
                    {confirmation && <span className="block font-normal text-muted-foreground">{t("team.invite.adminConfirmNote")}</span>}
                  </Label>
                </div>
              );
            })}
          </RadioGroup>
          {roleError && (
            <p id="invite-role-error" role="alert" className="text-sm font-medium text-destructive">
              {roleError}
            </p>
          )}
        </div>

        <p className="text-sm text-muted-foreground">{t("team.scopeLine", { scope: scopeLabel({ type: "ORGANIZATION" }, t) })}</p>

        <Alert>
          <Info className="h-4 w-4" aria-hidden />
          <AlertDescription>{t("team.invite.ownerNote")}</AlertDescription>
        </Alert>

        <Field label={t("team.invite.labelLabel")} htmlFor={labelId} error={labelError} hint={t("team.invite.labelHelp")}>
          <Input
            id={labelId}
            value={label}
            maxLength={INVITATION_LABEL_MAX}
            autoComplete="off"
            disabled={pending}
            className={fieldInputClass}
            onChange={(event) => {
              setLabel(event.target.value);
              setLabelError(undefined);
            }}
            {...errorProps(labelId, labelError)}
            aria-describedby={[labelError ? `${labelId}-error` : undefined, counterId].filter(Boolean).join(" ")}
          />
          <p id={counterId} className="text-right text-xs text-muted-foreground">
            {t("team.invite.labelCount", { n: label.length, max: INVITATION_LABEL_MAX })}
          </p>
        </Field>

        {typeof ttlDays === "number" && ttlDays > 0 && <p className="text-sm text-muted-foreground">{t("team.invite.validity", { days: ttlDays })}</p>}

        <FormAlert message={formError} />
        {!online && (
          <p id={offlineId} className="text-xs text-muted-foreground">
            {t("common.offlineAction")}
          </p>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" className="min-h-11" disabled={pending} onClick={() => onClose(false)}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" className="min-h-11" disabled={pending || blocked || !online || !role} aria-describedby={!online ? offlineId : undefined}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            {t("team.invite.create")}
          </Button>
        </div>
      </form>
    </ResponsiveDialog>
  );
}
