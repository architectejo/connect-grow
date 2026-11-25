import { Suspense, forwardRef, lazy, useCallback, useId, useImperativeHandle, useRef, useState } from "react";
import { Loader2, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationInternal, OrganizationInvitation, Uuid } from "@/api/types";
import { EmptyState, ErrorState } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIsMobile } from "@/hooks/use-mobile";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useInvitations } from "@/hooks/use-organization-team";
import { InvitationRow } from "./InvitationRow";

const RevokeInvitationDialog = lazy(() => import("./RevokeInvitationDialog").then((m) => ({ default: m.RevokeInvitationDialog })));

/** Poignée pour que la page replace le focus sur le titre de l'onglet (après une création de lien). */
export interface InvitationsPanelHandle {
  focusHeading: () => void;
}

interface InvitationsPanelProps {
  org: Pick<OrganizationInternal, "id" | "capabilities">;
  onAnnounce: (message: string) => void;
  /** Action de l'état vide : ouvre le dialogue d'invitation (le bouton est passé pour lui rendre le focus à la fermeture). */
  onInvite: (trigger?: HTMLElement) => void;
}

/**
 * Onglet « Invitations » : liste paginée des invitations en attente (20 par page). Monté seulement à l'ouverture de l'onglet,
 * donc la requête ne part pas avec la page. Hors ligne : liste conservée, boutons désactivés avec la raison.
 */
export const InvitationsPanel = forwardRef<InvitationsPanelHandle, InvitationsPanelProps>(function InvitationsPanel({ org, onAnnounce, onInvite }, ref) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const online = useOnlineStatus();
  const query = useInvitations(org.id);
  const [revoking, setRevoking] = useState<OrganizationInvitation | null>(null);
  const triggers = useRef(new Map<Uuid, HTMLButtonElement | null>());
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const offlineId = useId();
  const canRevoke = org.capabilities.includes("org.manage_members");

  useImperativeHandle(ref, () => ({ focusHeading: () => headingRef.current?.focus() }), []);

  const closeRevoke = useCallback((focusId?: Uuid) => {
    setRevoking(null);
    if (focusId) requestAnimationFrame(() => triggers.current.get(focusId)?.focus());
  }, []);
  const afterRevoked = useCallback(() => {
    setRevoking(null);
    // Le déclencheur disparaît avec la ligne : le focus va au titre de la liste
    requestAnimationFrame(() => headingRef.current?.focus());
  }, []);

  const invitations = query.data?.invitations ?? [];
  let body;
  if (query.isLoading) {
    body = (
      <div className="space-y-3" aria-busy="true">
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-28 w-full rounded-2xl md:h-16" />
        ))}
      </div>
    );
  } else if (query.isError && invitations.length === 0) {
    body = <ErrorState description={t("team.invitations.loadError")} onRetry={() => void query.refetch()} isRetrying={query.isFetching} />;
  } else if (invitations.length === 0) {
    body = (
      <EmptyState
        icon={UserPlus}
        description={t("team.invitations.empty")}
        action={
          <Button type="button" className="min-h-11" disabled={!online} onClick={(event) => onInvite(event.currentTarget)}>
            {t("team.invite.open")}
          </Button>
        }
      />
    );
  } else {
    const rows = invitations.map((invitation) => (
      <InvitationRow
        key={invitation.invitation_id}
        invitation={invitation}
        layout={isMobile ? "card" : "row"}
        canRevoke={canRevoke}
        online={online}
        offlineHintId={offlineId}
        triggerRef={(node) => {
          if (node) triggers.current.set(invitation.invitation_id, node);
          else triggers.current.delete(invitation.invitation_id);
        }}
        onRevoke={setRevoking}
      />
    ));
    body = isMobile ? (
      <ul className="space-y-3" aria-labelledby={headingId}>
        {rows}
      </ul>
    ) : (
      <div className="rounded-2xl border bg-card">
        <Table>
          <TableCaption className="sr-only">{t("team.invitations.caption")}</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">{t("team.invitations.colRole")}</TableHead>
              <TableHead scope="col">{t("team.invitations.colLabel")}</TableHead>
              <TableHead scope="col">{t("team.invitations.colCreatedBy")}</TableHead>
              <TableHead scope="col">{t("team.invitations.colExpires")}</TableHead>
              <TableHead scope="col">
                <span className="sr-only">{t("team.invitations.colActions")}</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>{rows}</TableBody>
        </Table>
      </div>
    );
  }

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 id={headingId} ref={headingRef} tabIndex={-1} className="font-display text-lg font-bold outline-none">
        {t("team.invitations.caption")}
      </h2>
      <p className="text-sm text-muted-foreground">{t("team.invitations.intro")}</p>
      {!online && (
        <p id={offlineId} className="text-xs text-muted-foreground">
          {t("common.offlineAction")}
        </p>
      )}
      {body}
      {query.hasNextPage && (
        <div className="flex flex-col items-center gap-2">
          <Button type="button" variant="outline" className="min-h-11" disabled={query.isFetchingNextPage || !online} onClick={() => void query.fetchNextPage()}>
            {query.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden />}
            {t("team.invitations.loadMore")}
          </Button>
          {query.isFetchNextPageError && (
            <p role="alert" className="text-sm text-destructive">
              {t("team.invitations.loadMoreError")}
            </p>
          )}
        </div>
      )}

      <Suspense fallback={null}>
        {revoking && (
          <RevokeInvitationDialog
            orgId={org.id}
            invitation={revoking}
            online={online}
            onClose={() => closeRevoke(revoking.invitation_id)}
            onRevoked={afterRevoked}
            onAnnounce={onAnnounce}
          />
        )}
      </Suspense>
    </section>
  );
});
