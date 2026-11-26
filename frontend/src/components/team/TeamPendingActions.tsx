import { Suspense, lazy, useCallback, useId, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AwaitingConfirmationInvitation, OrganizationInternal, Uuid } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useAwaitingConfirmations } from "@/hooks/use-organization-team";
import { AwaitingInvitationCard } from "./AwaitingInvitationCard";

// Les dialogues sont chargés à l'ouverture (réseau faible)
const ConfirmAdminInvitationDialog = lazy(() => import("./ConfirmAdminInvitationDialog").then((m) => ({ default: m.ConfirmAdminInvitationDialog })));
const RejectAdminInvitationDialog = lazy(() => import("./RejectAdminInvitationDialog").then((m) => ({ default: m.RejectAdminInvitationDialog })));

interface TeamPendingActionsProps {
  org: Pick<OrganizationInternal, "id" | "name" | "capabilities">;
  onAnnounce: (message: string) => void;
  /** Cible de focus quand la section disparaît après une action (titre de la liste des membres). */
  onFocusFallback: () => void;
}

type OpenDialog = { kind: "confirm" | "reject"; invitation: AwaitingConfirmationInvitation } | null;

/**
 * Section « À traiter » de l'écran Équipe (spec D2 §4.4). F2-bis : groupe « Demandes d'accès à confirmer » (seulement avec
 * `org.manage_members`). Les groupes de nominations (F5) viendront s'ajouter ici. Rendue seulement si elle contient une carte,
 * ou une erreur de chargement (ligne compacte + « Réessayer ») ; rien pendant le chargement.
 */
export function TeamPendingActions({ org, onAnnounce, onFocusFallback }: TeamPendingActionsProps) {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  const canManage = org.capabilities.includes("org.manage_members");
  const query = useAwaitingConfirmations(org.id, canManage);
  const [dialog, setDialog] = useState<OpenDialog>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const triggers = useRef(new Map<Uuid, HTMLButtonElement | null>());
  const headingId = useId();
  const groupId = useId();
  const offlineId = useId();
  const invitations = query.data?.invitations ?? [];

  const close = useCallback(() => {
    const id = dialog?.invitation.invitation_id;
    setDialog(null);
    if (id) requestAnimationFrame(() => triggers.current.get(id)?.focus());
  }, [dialog]);

  const done = useCallback(() => {
    // La carte déclencheuse disparaît : titre « À traiter » s'il reste des cartes, sinon la liste des membres
    const remaining = invitations.length - 1;
    setDialog(null);
    requestAnimationFrame(() => {
      if (remaining > 0 && headingRef.current?.isConnected) headingRef.current.focus();
      else onFocusFallback();
    });
  }, [invitations.length, onFocusFallback]);

  if (!canManage) return null;
  const failed = query.isError && invitations.length === 0;
  if (!failed && invitations.length === 0) {
    // Chargement ou vide : section absente (on n'annonce pas une section peut-être vide)
    return null;
  }

  return (
    <section aria-labelledby={headingId} className="mb-6 space-y-3">
      <h2 id={headingId} ref={headingRef} tabIndex={-1} className="font-display text-lg font-bold outline-none">
        {t("team.pending.title")}
      </h2>
      {failed ? (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-3 text-sm">
          <p className="flex-1">{t("team.pending.loadError")}</p>
          <Button type="button" variant="outline" className="min-h-11" disabled={query.isFetching} onClick={() => void query.refetch()}>
            {query.isFetching && <Loader2 className="animate-spin" aria-hidden />}
            {t("states.retry")}
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <h3 id={groupId} className="text-base font-semibold">
            {t("team.pending.toConfirm")}
          </h3>
          {!online && (
            <p id={offlineId} className="text-xs text-muted-foreground">
              {t("common.offlineAction")}
            </p>
          )}
          <ul className="space-y-3" aria-labelledby={groupId}>
            {invitations.map((invitation) => (
              <AwaitingInvitationCard
                key={invitation.invitation_id}
                invitation={invitation}
                online={online}
                offlineHintId={offlineId}
                confirmRef={(node) => {
                  if (node) triggers.current.set(invitation.invitation_id, node);
                  else triggers.current.delete(invitation.invitation_id);
                }}
                onConfirm={(item) => setDialog({ kind: "confirm", invitation: item })}
                onReject={(item) => setDialog({ kind: "reject", invitation: item })}
              />
            ))}
          </ul>
          {query.hasNextPage && (
            <Button type="button" variant="outline" className="min-h-11" disabled={query.isFetchingNextPage || !online} onClick={() => void query.fetchNextPage()}>
              {query.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden />}
              {t("team.pending.loadMore")}
            </Button>
          )}
        </div>
      )}

      <Suspense fallback={null}>
        {dialog?.kind === "confirm" && (
          <ConfirmAdminInvitationDialog
            orgId={org.id}
            orgName={org.name}
            invitation={dialog.invitation}
            online={online}
            onClose={close}
            onDone={done}
            onAnnounce={onAnnounce}
          />
        )}
        {dialog?.kind === "reject" && (
          <RejectAdminInvitationDialog orgId={org.id} invitation={dialog.invitation} online={online} onClose={close} onDone={done} onAnnounce={onAnnounce} />
        )}
      </Suspense>
    </section>
  );
}
