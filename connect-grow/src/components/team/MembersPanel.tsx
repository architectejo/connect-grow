import { Suspense, lazy, useCallback, useId, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationInternal, OrganizationMember, Uuid } from "@/api/types";
import { EmptyState, ErrorState } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIsMobile } from "@/hooks/use-mobile";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useMembers } from "@/hooks/use-organization-team";
import type { TeamAction } from "@/lib/team";
import { MemberRow } from "./MemberRow";

// Les fenêtres sont chargées à l'ouverture, pas avec la page (réseau faible)
const ChangeRoleDialog = lazy(() => import("./ChangeRoleDialog").then((m) => ({ default: m.ChangeRoleDialog })));
const TransferOwnershipDialog = lazy(() => import("./TransferOwnershipDialog").then((m) => ({ default: m.TransferOwnershipDialog })));
const RemoveMemberDialog = lazy(() => import("./RemoveMemberDialog").then((m) => ({ default: m.RemoveMemberDialog })));

interface MembersPanelProps {
  org: Pick<OrganizationInternal, "id" | "my_role" | "capabilities">;
  /** Texte annoncé par la région `aria-live` de la page. */
  onAnnounce: (message: string) => void;
}

type OpenDialog = { action: TeamAction; member: OrganizationMember } | null;

/**
 * Liste paginée des membres (20 par page, « Voir plus ») et fenêtres d'action. Cartes sur mobile, tableau sur ordinateur.
 * Hors ligne : la liste déjà chargée reste affichée, les actions sont désactivées avec la raison.
 */
export function MembersPanel({ org, onAnnounce }: MembersPanelProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const online = useOnlineStatus();
  const query = useMembers(org.id);
  const [dialog, setDialog] = useState<OpenDialog>(null);
  const triggers = useRef(new Map<Uuid, HTMLButtonElement | null>());
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const offlineId = useId();
  const actor = { role: org.my_role, capabilities: org.capabilities };

  const close = useCallback(
    (focusMemberId?: Uuid) => {
      setDialog(null);
      // Le bouton ⋯ de la ligne récupère le focus (le déclencheur Radix est démonté avec le menu)
      if (focusMemberId) requestAnimationFrame(() => triggers.current.get(focusMemberId)?.focus());
    },
    [],
  );
  const closeAfterRemoval = useCallback(() => {
    setDialog(null);
    requestAnimationFrame(() => headingRef.current?.focus());
  }, []);

  const members = query.data?.members ?? [];
  let body;
  if (query.isLoading) {
    body = (
      <div className="space-y-3" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24 w-full rounded-2xl md:h-16" />
        ))}
      </div>
    );
  } else if (query.isError && members.length === 0) {
    body = <ErrorState description={t("team.loadError")} onRetry={() => void query.refetch()} isRetrying={query.isFetching} />;
  } else if (members.length === 0) {
    body = <EmptyState description={t("team.empty")} />;
  } else {
    const rows = members.map((member) => (
      <MemberRow
        key={member.membership_id}
        member={member}
        actor={actor}
        layout={isMobile ? "card" : "row"}
        online={online}
        offlineHintId={offlineId}
        triggerRef={(node) => {
          if (node) triggers.current.set(member.membership_id, node);
          else triggers.current.delete(member.membership_id);
        }}
        onAction={(action, target) => setDialog({ action, member: target })}
      />
    ));
    body = isMobile ? (
      <ul className="space-y-3" aria-labelledby={headingId}>
        {rows}
      </ul>
    ) : (
      <div className="rounded-2xl border bg-card">
        <Table>
          <TableCaption className="sr-only">{t("team.listCaption")}</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">{t("team.colMember")}</TableHead>
              <TableHead scope="col">{t("team.colRole")}</TableHead>
              <TableHead scope="col">{t("team.colSince")}</TableHead>
              <TableHead scope="col">
                <span className="sr-only">{t("team.colActions")}</span>
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
        {t("team.listCaption")}
      </h2>
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
            {t("team.loadMore")}
          </Button>
          {query.isFetchNextPageError && (
            <p role="alert" className="text-sm text-destructive">
              {t("team.loadMoreError")}
            </p>
          )}
        </div>
      )}

      <Suspense fallback={null}>
        {dialog?.action === "changeRole" && (
          <ChangeRoleDialog
            orgId={org.id}
            member={dialog.member}
            actorRole={org.my_role}
            online={online}
            onClose={() => close(dialog.member.membership_id)}
            onAnnounce={onAnnounce}
          />
        )}
        {dialog?.action === "transfer" && (
          <TransferOwnershipDialog
            orgId={org.id}
            target={dialog.member}
            online={online}
            onClose={() => close(dialog.member.membership_id)}
            onAnnounce={onAnnounce}
          />
        )}
        {dialog?.action === "remove" && (
          <RemoveMemberDialog
            orgId={org.id}
            member={dialog.member}
            online={online}
            onClose={() => close(dialog.member.membership_id)}
            onRemoved={closeAfterRemoval}
            onAnnounce={onAnnounce}
          />
        )}
      </Suspense>
    </section>
  );
}
