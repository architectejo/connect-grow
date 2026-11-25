import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2, MailOpen, XCircle } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { InvitationAccepted, InvitationPreview } from "@/api/types";
import { RoleBadge, SellerTypeBadge, UserAvatar } from "@/components/common";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useAuth } from "@/contexts/AuthContext";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useAcceptInvitation, useDeclineInvitation, useInvitationPreview } from "@/hooks/use-organization-team";
import { useRateBlock } from "@/components/team/use-rate-block";
import { loginPath } from "@/lib/auth-paths";
import { formatLongDate } from "@/lib/format";
import { INVITATION_PATH, clearInvitationToken, ingestInvitationToken } from "@/lib/invitation-token";
import { classifyInvitationError, clearsTokenOnFailure, type InvitationFailure } from "@/lib/invitations";

// Le dialogue de refus est chargé à son ouverture (réseau faible)
const DeclineDialog = lazy(() => import("@/components/team/DeclineInvitationDialog").then((m) => ({ default: m.DeclineInvitationDialog })));

type Outcome = { kind: "joined"; data: InvitationAccepted } | { kind: "declined" } | { kind: "error"; failure: InvitationFailure };

/** Écran affiché ; les écrans « joined » et « preview » portent leurs données, ce qui évite tout cast. */
type View = { name: "joined"; data: InvitationAccepted } | { name: "preview"; data: InvitationPreview } | { name: "declined" | "missing" | "guest" | "loading" | "error" };

const cardClass = "rounded-2xl border bg-card p-6 shadow-soft";

/** `Referrer-Policy: no-referrer` pour cette page (balise meta, retirée au départ) : aucun lien sortant ne transmet l'adresse. */
function useNoReferrer() {
  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "referrer";
    meta.content = "no-referrer";
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);
}

/**
 * E15 : page publique d'acceptation d'une invitation d'organisation (`/organization-invitation#token=…`).
 *
 * Le jeton est lu dans le fragment, rangé en `sessionStorage`, et la barre d'adresse est nettoyée avant tout appel. Il ne voyage
 * que dans le corps d'un POST (il est relu dans le stockage au moment de l'appel : jamais une clé de requête, une variable de
 * mutation, un toast, une région `aria-live` ni un journal). Un visiteur non connecté ne voit ni nom d'organisation ni rôle.
 */
const OrganizationInvitation = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { contexts, setActive } = useActiveContext();
  useNoReferrer();

  // Avant tout rendu et tout appel : fragment -> sessionStorage -> adresse nettoyée. On ne garde ici qu'un booléen.
  // Initialiseur (et non effet) volontaire : il s'exécute avant le premier rendu, donc avant le premier appel d'aperçu, qui
  // partirait sinon sans jeton. Relancé par StrictMode, il reste sûr : le jeton est alors relu depuis le stockage.
  const [hasToken, setHasToken] = useState(() => ingestInvitationToken() !== null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [rateBlocked, blockRate] = useRateBlock();
  const headingRef = useRef<HTMLHeadingElement>(null);

  const preview = useInvitationPreview(!authLoading && isAuthenticated && hasToken && !outcome);
  const accept = useAcceptInvitation();
  const decline = useDeclineInvitation();

  const failure: InvitationFailure | null = outcome?.kind === "error" ? outcome.failure : preview.isError ? classifyInvitationError(preview.error) : null;
  // 401 : la session a expiré, retour à l'écran visiteur (le jeton reste rangé)
  const asGuest = !isAuthenticated || failure?.kind === "unauthenticated";

  // Le jeton est supprimé après un jeton invalide ou une appartenance existante ; conservé sur toute autre erreur
  const failureKind = failure?.kind;
  useEffect(() => {
    if (failureKind && clearsTokenOnFailure(failureKind)) {
      clearInvitationToken();
      setHasToken(false);
    }
  }, [failureKind]);

  const retryAfter = failure?.kind === "rate" ? failure.retryAfter : undefined;
  useEffect(() => {
    // Sans délai lisible, « Réessayer » reste disponible
    if (retryAfter !== undefined) blockRate(retryAfter);
  }, [retryAfter, blockRate]);

  let view: View;
  if (outcome?.kind === "joined") view = { name: "joined", data: outcome.data };
  else if (outcome?.kind === "declined") view = { name: "declined" };
  else if (failure && !asGuest) view = { name: "error" };
  else if (!hasToken) view = { name: "missing" };
  else if (authLoading) view = { name: "loading" };
  else if (asGuest) view = { name: "guest" };
  else if (preview.isPending || !preview.data) view = { name: "loading" };
  else view = { name: "preview", data: preview.data };
  const viewName = view.name;

  // Le titre reçoit le focus à chaque changement d'état (lecteurs d'écran, clavier)
  useEffect(() => {
    if (viewName !== "loading") headingRef.current?.focus();
  }, [viewName]);
  useEffect(() => {
    if (viewName === "joined") setAnnouncement(t("invitation.joined.announce"));
  }, [viewName, t]);

  const busy = accept.isPending || decline.isPending;

  const onAccept = async () => {
    if (busy || !online) return;
    try {
      const data = await accept.mutateAsync();
      setHasToken(false);
      setOutcome({ kind: "joined", data });
    } catch (error) {
      setOutcome({ kind: "error", failure: classifyInvitationError(error) });
    }
  };

  const onDecline = async () => {
    if (busy || !online) return;
    try {
      await decline.mutateAsync();
      setHasToken(false);
      setDeclineOpen(false);
      setOutcome({ kind: "declined" });
    } catch (error) {
      setDeclineOpen(false);
      setOutcome({ kind: "error", failure: classifyInvitationError(error) });
    }
  };

  const retry = () => {
    setOutcome(null);
    void preview.refetch();
  };

  const openOrganization = (organizationId: string) => {
    // Le profil actif ne change qu'à cet appui (l'utilisateur sait sous quelle identité il agit)
    if (contexts.some((c) => c.type === "ORGANIZATION" && c.id === organizationId)) setActive({ type: "ORGANIZATION", id: organizationId });
    navigate(`/organizations/${organizationId}`);
  };

  const heading = (text: string, icon?: ReactNode) => (
    <div className="flex flex-col items-center gap-3 text-center">
      {icon}
      <h1 ref={headingRef} tabIndex={-1} className="text-balance text-2xl font-extrabold outline-none">
        {text}
      </h1>
    </div>
  );

  const errorCard = (title: string, body: string, action: ReactNode) => (
    <section role="alert" className={cardClass}>
      {heading(title, <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden />)}
      <p className="mt-3 text-center text-sm text-muted-foreground">{body}</p>
      <div className="mt-6 flex flex-col gap-2">{action}</div>
    </section>
  );
  const homeButton = (
    <Button asChild variant="outline" className="min-h-12 w-full">
      <Link to="/">{t("invitation.backHome")}</Link>
    </Button>
  );
  const profilesButton = (
    <Button asChild className="min-h-12 w-full">
      <Link to="/profiles">{t("invitation.err.profiles")}</Link>
    </Button>
  );

  let content: ReactNode;
  switch (view.name) {
    case "loading":
      content = (
        <div className={cardClass} aria-busy="true" aria-label={t("invitation.loading")}>
          <Skeleton className="mx-auto h-16 w-16 rounded-xl" />
          <Skeleton className="mx-auto mt-4 h-6 w-3/4" />
          <Skeleton className="mt-6 h-20 w-full" />
          <Skeleton className="mt-6 h-12 w-full rounded-xl" />
        </div>
      );
      break;
    case "missing":
      content = errorCard(t("invitation.err.missing.title"), t("invitation.err.missing.body"), homeButton);
      break;
    case "guest":
      // Aucun appel API, aucun nom d'organisation, aucun rôle, aucune date
      content = (
        <section className={cardClass}>
          {heading(t("invitation.guest.title"), <MailOpen className="h-10 w-10 text-primary" aria-hidden />)}
          <p className="mt-3 text-center text-sm text-muted-foreground">{t("invitation.guest.body")}</p>
          <div className="mt-6 flex flex-col gap-2">
            <Button asChild className="min-h-12 w-full">
              <Link to={loginPath(INVITATION_PATH)}>{t("invitation.guest.login")}</Link>
            </Button>
            <Button asChild variant="outline" className="min-h-12 w-full">
              <Link to={`/register?next=${encodeURIComponent(INVITATION_PATH)}`}>{t("invitation.guest.register")}</Link>
            </Button>
          </div>
          <p className="mt-4 text-center text-xs text-muted-foreground">{t("invitation.guest.caution")}</p>
        </section>
      );
      break;
    case "joined": {
      const { data } = view;
      content = (
        <section className={cardClass}>
          {heading(t("invitation.joined.title", { name: data.organization_name }), <CheckCircle2 className="h-10 w-10 text-primary" aria-hidden />)}
          <p className="mt-3 text-center text-sm text-muted-foreground">{t("invitation.joined.body", { role: t(`role.${data.role}`) })}</p>
          <div className="mt-6 flex flex-col gap-2">
            <Button type="button" className="min-h-12 w-full" onClick={() => openOrganization(data.organization_id)}>
              {t("invitation.joined.open")}
            </Button>
            <Button asChild variant="ghost" className="min-h-12 w-full">
              <Link to="/dashboard">{t("invitation.joined.stay")}</Link>
            </Button>
          </div>
        </section>
      );
      break;
    }
    case "declined":
      content = (
        <section className={cardClass}>
          {heading(t("invitation.declined.title"), <XCircle className="h-10 w-10 text-muted-foreground" aria-hidden />)}
          <p className="mt-3 text-center text-sm text-muted-foreground">{t("invitation.declined.body")}</p>
          <div className="mt-6 flex flex-col gap-2">{homeButton}</div>
        </section>
      );
      break;
    case "preview": {
      const { data } = view;
      content = (
        <section className={cardClass}>
          <h1 ref={headingRef} tabIndex={-1} className="text-balance text-center text-xl font-extrabold outline-none">
            {t("invitation.preview.title")}
          </h1>
          <div className="mt-5 flex flex-col items-center gap-2 text-center">
            <UserAvatar name={data.organization_name} shape="square" size="lg" />
            <h2 className="max-w-full truncate text-lg font-bold" title={data.organization_name} aria-label={data.organization_name}>
              {data.organization_name}
            </h2>
            <SellerTypeBadge contextType="ORGANIZATION" orgType={data.org_type} />
          </div>
          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted-foreground">{t("invitation.preview.invitedBy")}</dt>
              <dd className="font-semibold">{data.invited_by_display_name}</dd>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">{t("invitation.preview.role")}</dt>
                <dd>
                  <RoleBadge role={data.role} />
                </dd>
              </div>
              <p className="text-xs text-muted-foreground">{t(`role.${data.role}_desc`)}</p>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted-foreground">{t("invitation.preview.validUntil")}</dt>
              <dd className="font-semibold">{formatLongDate(data.expires_at)}</dd>
            </div>
          </dl>
          <p className="mt-5 text-sm text-muted-foreground">{t("invitation.preview.body")}</p>
          {!online && <p className="mt-3 text-xs text-muted-foreground">{t("common.offlineAction")}</p>}
          <div className="mt-5 flex flex-col gap-2">
            <Button type="button" className="min-h-12 w-full" disabled={busy || !online} onClick={() => void onAccept()}>
              {accept.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t("invitation.accept")}
            </Button>
            <Button type="button" variant="outline" className="min-h-12 w-full" disabled={busy || !online} onClick={() => setDeclineOpen(true)}>
              {t("invitation.decline")}
            </Button>
          </div>
        </section>
      );
      break;
    }
    default: {
      // « error » : le détail vient de failure.kind
      switch (failure?.kind) {
        case "invalid":
          content = errorCard(t("invitation.err.invalid.title"), t("invitation.err.invalid.body"), homeButton);
          break;
        case "phone":
          content = errorCard(
            t("invitation.err.phone.title"),
            t("invitation.err.phone.body"),
            <Button asChild className="min-h-12 w-full">
              <Link to="/settings?tab=contact">{t("invitation.err.phone.action")}</Link>
            </Button>,
          );
          break;
        case "limit":
          content = errorCard(t("invitation.err.limit.title"), t("invitation.err.limit.body"), profilesButton);
          break;
        case "member":
          content = errorCard(t("invitation.err.member.title"), t("invitation.err.member.body"), profilesButton);
          break;
        case "security":
          content = errorCard(t("invitation.err.security.title"), t("errors.deny.SECURITY.action"), homeButton);
          break;
        case "rate":
          content = errorCard(
            t("invitation.err.rate.title"),
            t("invitation.err.rate.body"),
            <Button type="button" className="min-h-12 w-full" disabled={rateBlocked} onClick={retry}>
              {t("invitation.retry")}
            </Button>,
          );
          break;
        case "network":
          content = errorCard(
            t("invitation.err.network.title"),
            t("invitation.err.network.body"),
            <Button type="button" className="min-h-12 w-full" onClick={retry}>
              {t("invitation.retry")}
            </Button>,
          );
          break;
        default:
          content = errorCard(
            t("invitation.err.generic.title"),
            t("invitation.err.generic.body"),
            <Button type="button" className="min-h-12 w-full" onClick={retry}>
              {t("invitation.retry")}
            </Button>,
          );
      }
    }
  }

  return (
    <AppShell withFooter={false}>
      <div className="mx-auto max-w-md py-6">
        {/* Région d'annonce unique de la page : jamais le jeton ni un nom */}
        <div role="status" aria-live="polite" className="sr-only">
          {announcement}
        </div>
        {content}
      </div>
      <Suspense fallback={null}>
        {declineOpen && <DeclineDialog pending={decline.isPending} onKeep={() => setDeclineOpen(false)} onDecline={() => void onDecline()} />}
      </Suspense>
    </AppShell>
  );
};

export default OrganizationInvitation;
