import { Suspense, lazy, useCallback, useId, useRef, useState } from "react";
import { Clock, Hourglass, KeyRound, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { MyAwaitingInvitation, Uuid } from "@/api/types";
import { RoleBadge, SellerTypeBadge, UserAvatar } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useMyAwaitingInvitations } from "@/hooks/use-my-awaiting-invitations";
import { formatDateTime } from "@/lib/format";
import { scopeLabel } from "@/lib/team";

const NewConfirmationCodeDialog = lazy(() => import("./NewConfirmationCodeDialog").then((m) => ({ default: m.NewConfirmationCodeDialog })));
const WithdrawAwaitingDialog = lazy(() => import("./WithdrawAwaitingDialog").then((m) => ({ default: m.WithdrawAwaitingDialog })));

interface AwaitingMembershipsSectionProps {
  onAnnounce: (message: string) => void;
  /** Cible de focus quand la section disparaît (titre « Organisations »). */
  onFocusFallback: () => void;
}

type OpenDialog = { kind: "code" | "withdraw"; invitation: MyAwaitingInvitation } | null;

/**
 * E17 : « Demandes en attente de confirmation » sur `/profiles` (spec D2 §11). Rendue seulement si la liste n'est pas vide ;
 * rien pendant le chargement ni en cas d'erreur (information secondaire). La liste ne contient jamais de code.
 */
export function AwaitingMembershipsSection({ onAnnounce, onFocusFallback }: AwaitingMembershipsSectionProps) {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  const query = useMyAwaitingInvitations();
  const [dialog, setDialog] = useState<OpenDialog>(null);
  const codeTriggers = useRef(new Map<Uuid, HTMLButtonElement | null>());
  const withdrawTriggers = useRef(new Map<Uuid, HTMLButtonElement | null>());
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const offlineId = useId();
  const invitations = query.data?.invitations ?? [];

  const closeTo = useCallback((triggers: Map<Uuid, HTMLButtonElement | null>, id: Uuid) => {
    setDialog(null);
    requestAnimationFrame(() => triggers.get(id)?.focus());
  }, []);

  const afterRemoval = useCallback(() => {
    const remaining = invitations.length - 1;
    setDialog(null);
    requestAnimationFrame(() => {
      if (remaining > 0 && headingRef.current?.isConnected) headingRef.current.focus();
      else onFocusFallback();
    });
  }, [invitations.length, onFocusFallback]);

  if (invitations.length === 0) return null;

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 id={headingId} ref={headingRef} tabIndex={-1} className="flex items-center gap-2 font-display text-lg font-bold outline-none">
        <Hourglass className="h-5 w-5 text-primary" aria-hidden /> {t("profiles.awaiting.title")}
      </h2>
      <p className="text-sm text-muted-foreground">{t("profiles.awaiting.intro")}</p>
      {!online && (
        <p id={offlineId} className="text-xs text-muted-foreground">
          {t("common.offlineAction")}
        </p>
      )}
      <ul className="grid gap-3">
        {invitations.map((invitation) => {
          const name = invitation.organization_name;
          const expired = invitation.status === "EXPIRED";
          return (
            <li key={invitation.invitation_id}>
              <article className="flex flex-col gap-3 rounded-2xl border bg-card p-4 shadow-soft">
                <div className="flex items-start gap-3">
                  <UserAvatar name={name} size="md" shape="square" />
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate font-semibold" title={name}>
                      {name}
                    </h3>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <SellerTypeBadge contextType="ORGANIZATION" orgType={invitation.org_type} />
                      <RoleBadge role={invitation.role} />
                      <span className="text-xs text-muted-foreground">{scopeLabel(invitation.scope ?? { type: "ORGANIZATION" }, t)}</span>
                    </div>
                  </div>
                </div>
                {expired ? (
                  <div className="space-y-1">
                    <Badge variant="outline" className="gap-1">
                      <Clock className="h-3.5 w-3.5" aria-hidden />
                      {t("profiles.awaiting.expired")}
                    </Badge>
                    <p className="text-sm text-muted-foreground">{t("profiles.awaiting.expiredHint")}</p>
                  </div>
                ) : (
                  <>
                    <div className="space-y-1 text-sm text-muted-foreground">
                      <p>{t("profiles.awaiting.acceptedAt", { date: formatDateTime(invitation.accepted_at) })}</p>
                      <p>{t("profiles.awaiting.deadline", { date: formatDateTime(invitation.confirmation_expires_at) })}</p>
                      <p className="text-xs">{t("profiles.awaiting.codeHint")}</p>
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <Button
                        ref={(node) => {
                          if (node) codeTriggers.current.set(invitation.invitation_id, node);
                          else codeTriggers.current.delete(invitation.invitation_id);
                        }}
                        type="button"
                        variant="outline"
                        className="min-h-11 w-full sm:w-auto"
                        disabled={!online}
                        aria-describedby={!online ? offlineId : undefined}
                        aria-label={t("profiles.awaiting.newCodeAria", { name })}
                        onClick={() => setDialog({ kind: "code", invitation })}
                      >
                        <KeyRound aria-hidden />
                        {t("profiles.awaiting.newCode")}
                      </Button>
                      <Button
                        ref={(node) => {
                          if (node) withdrawTriggers.current.set(invitation.invitation_id, node);
                          else withdrawTriggers.current.delete(invitation.invitation_id);
                        }}
                        type="button"
                        variant="ghost"
                        className="min-h-11 w-full text-destructive hover:text-destructive sm:w-auto"
                        disabled={!online}
                        aria-describedby={!online ? offlineId : undefined}
                        aria-label={t("profiles.awaiting.withdrawAria", { name })}
                        onClick={() => setDialog({ kind: "withdraw", invitation })}
                      >
                        {t("profiles.awaiting.withdraw")}
                      </Button>
                    </div>
                  </>
                )}
              </article>
            </li>
          );
        })}
      </ul>
      {query.hasNextPage && (
        <Button type="button" variant="outline" className="min-h-11" disabled={query.isFetchingNextPage || !online} onClick={() => void query.fetchNextPage()}>
          {query.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden />}
          {t("profiles.awaiting.loadMore")}
        </Button>
      )}

      <Suspense fallback={null}>
        {dialog?.kind === "code" && (
          <NewConfirmationCodeDialog
            invitation={dialog.invitation}
            online={online}
            onClose={() => closeTo(codeTriggers.current, dialog.invitation.invitation_id)}
            onGone={afterRemoval}
            onAnnounce={onAnnounce}
          />
        )}
        {dialog?.kind === "withdraw" && (
          <WithdrawAwaitingDialog
            invitationId={dialog.invitation.invitation_id}
            organizationName={dialog.invitation.organization_name}
            online={online}
            onClose={() => closeTo(withdrawTriggers.current, dialog.invitation.invitation_id)}
            onWithdrawn={() => {
              const message = t("profiles.awaiting.withdrawn");
              toast.success(message);
              onAnnounce(message);
              afterRemoval();
            }}
            onGone={afterRemoval}
          />
        )}
      </Suspense>
    </section>
  );
}
