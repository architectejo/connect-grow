import { Suspense, lazy, useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Hourglass, Info, Loader2, MailOpen, UserCheck, XCircle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { InvitableRole, InvitationJoined, InvitationPreview, Uuid } from "@/api/types";
import { RoleBadge, SellerTypeBadge, UserAvatar } from "@/components/common";
import { RoleAccessList } from "@/components/invitations/RoleAccessList";
import { ConfirmationCodeDisplay } from "@/components/team/ConfirmationCodeDisplay";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useAuth } from "@/contexts/AuthContext";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { invalidateContexts } from "@/hooks/use-contexts";
import { INVITATION_PREVIEW_KEY, useAcceptInvitation, useDeclineInvitation, useInvitationPreview } from "@/hooks/use-organization-team";
import { useRateBlock } from "@/components/team/use-rate-block";
import { loginPath } from "@/lib/auth-paths";
import { formatDateTime, formatLongDate } from "@/lib/format";
import { INVITATION_PATH, clearInvitationToken, hasTokenParam, ingestInvitationToken, readInvitationToken } from "@/lib/invitation-token";
import { classifyInvitationError, clearsTokenOnFailure, type InvitationFailure } from "@/lib/invitations";
import { scopeLabel } from "@/lib/team";

// Le dialogue de refus est chargé à son ouverture (réseau faible)
const DeclineDialog = lazy(() => import("@/components/team/DeclineInvitationDialog").then((m) => ({ default: m.DeclineInvitationDialog })));
const WithdrawDialog = lazy(() => import("@/components/profiles/WithdrawAwaitingDialog").then((m) => ({ default: m.WithdrawAwaitingDialog })));

/**
 * Réponse 202 telle que l'écran la garde : le code de rattachement n'existe QUE dans cet état local (effacé au démontage,
 * au retrait de la demande) ; la mutation qui l'a reçu est remise à zéro aussitôt.
 */
interface AwaitingOutcome {
  invitationId: Uuid;
  organizationName: string;
  role: InvitableRole;
  confirmationExpiresAt: string;
  code: string;
}

type Outcome =
  | { kind: "joined"; data: InvitationJoined }
  | { kind: "awaiting"; data: AwaitingOutcome }
  | { kind: "withdrawn" }
  | { kind: "declined" }
  | { kind: "error"; failure: InvitationFailure };

/** Écran affiché ; les écrans « joined », « awaiting » et « preview » portent leurs données, ce qui évite tout cast. */
type View =
  | { name: "joined"; data: InvitationJoined }
  | { name: "awaiting"; data: AwaitingOutcome }
  | { name: "preview"; data: InvitationPreview }
  | { name: "declined" | "withdrawn" | "missing" | "guest" | "loading" | "error" };

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
 *
 * Rôle Administrateur (F2-bis) : l'acceptation répond 202 avec un code de rattachement à 6 chiffres, affiché une seule fois
 * (écran « Demande envoyée ») et gardé seulement dans l'état local de la page : jamais annoncé, ni en toast, ni stocké, ni en cache.
 */
const OrganizationInvitation = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { isAuthenticated, isLoading: authLoading, user, refreshUser } = useAuth();
  const { contexts, setActive, isError: contextsError } = useActiveContext();
  useNoReferrer();

  // Avant tout rendu et tout appel : fragment -> sessionStorage -> adresse nettoyée. On ne garde ici qu'un booléen.
  // Initialiseur (et non effet) volontaire : il s'exécute avant le premier rendu, donc avant le premier appel d'aperçu, qui
  // partirait sinon sans jeton. Relancé par StrictMode, il reste sûr : le jeton est alors relu depuis le stockage.
  const [hasToken, setHasToken] = useState(() => ingestInvitationToken() !== null || readInvitationToken() !== null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const withdrawButton = useRef<HTMLButtonElement>(null);
  const codeHeadingId = useId();
  const confirmNoteId = useId();
  const [announcement, setAnnouncement] = useState("");
  const [rateBlocked, blockRate] = useRateBlock();
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Jeton utilisable par CE compte : expiré (60 min), lié à un autre compte ou effacé par une fin de session (401 →
  // `clearSession`), il n'est plus utilisable et la page affiche « Lien incomplet » (lien à rouvrir).
  // Lecture pendant le rendu volontaire : `readInvitationToken` est idempotente (un jeton périmé est effacé une fois,
  // les lectures suivantes renvoient null) et ne lit qu'une petite entrée de `sessionStorage`.
  const accountId = user?.id;
  const tokenUsable = hasToken && readInvitationToken(accountId) !== null;
  // Session ouverte mais compte inconnu (`accounts/me/` en échec) : aucun aperçu sans compte à qui lier le jeton
  const accountUnknown = isAuthenticated && !authLoading && !user;

  /**
   * Un fragment `#token=` (arrivée, ou second lien ouvert dans le même onglet) : rangé, puis la location du routeur est
   * réalignée (`replace`) pour que le jeton ne reste ni dans l'historique ni dans l'état de React Router.
   */
  const takeLinkFromHash = useCallback(
    (hash: string) => {
      if (!hasTokenParam(hash)) return;
      const fresh = ingestInvitationToken(hash);
      if (fresh) {
        // Nouveau lien : on repart de zéro (aucun aperçu, aucune issue d'un lien précédent)
        queryClient.removeQueries({ queryKey: INVITATION_PREVIEW_KEY });
        setOutcome(null);
        setDeclineOpen(false);
        setHasToken(true);
      }
      navigate(INVITATION_PATH, { replace: true });
    },
    [navigate, queryClient],
  );
  // Effet normal : la barre d'adresse est déjà nettoyée par l'initialiseur ; ici on réaligne seulement la location du routeur.
  useEffect(() => {
    takeLinkFromHash(location.hash);
  }, [location.hash, takeLinkFromHash]);
  useEffect(() => {
    const onHashChange = () => takeLinkFromHash(window.location.hash);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [takeLinkFromHash]);

  const preview = useInvitationPreview(!authLoading && isAuthenticated && !!user && tokenUsable && !outcome);
  const accept = useAcceptInvitation();
  const decline = useDeclineInvitation();

  const failure: InvitationFailure | null =
    outcome?.kind === "error"
      ? outcome.failure
      : accountUnknown
        ? { kind: "generic" }
        : preview.isError
          ? classifyInvitationError(preview.error)
          : null;
  // 401 : la session a expiré. `clearSession` a effacé le jeton (audit S2) : la page tombe sur « Lien incomplet » ci-dessous.
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
  else if (outcome?.kind === "awaiting") view = { name: "awaiting", data: outcome.data };
  else if (outcome?.kind === "withdrawn") view = { name: "withdrawn" };
  else if (outcome?.kind === "declined") view = { name: "declined" };
  else if (failure && !asGuest) view = { name: "error" };
  else if (!tokenUsable) view = { name: "missing" };
  else if (authLoading) view = { name: "loading" };
  else if (asGuest) view = { name: "guest" };
  else if (preview.isPending || !preview.data) view = { name: "loading" };
  else view = { name: "preview", data: preview.data };
  const viewName = view.name;
  // Une erreur qui en remplace une autre change aussi d'écran : le focus suit
  const focusKey = viewName === "error" ? `error:${failure?.kind}` : viewName;

  // Le titre reçoit le focus à chaque changement d'état (lecteurs d'écran, clavier)
  useEffect(() => {
    if (focusKey !== "loading") headingRef.current?.focus();
  }, [focusKey]);
  useEffect(() => {
    if (viewName === "joined") setAnnouncement(t("invitation.joined.announce"));
    // Jamais le code dans l'annonce : seulement « code affiché à l'écran »
    if (viewName === "awaiting") setAnnouncement(t("invitation.awaiting.announce"));
  }, [viewName, t]);

  const busy = accept.isPending || decline.isPending;

  const onAccept = async () => {
    if (busy || !online) return;
    try {
      const data = await accept.mutateAsync();
      setHasToken(false);
      if (data.status === "AWAITING_CONFIRMATION") {
        // Le code passe dans l'état local de l'écran ; la mutation (et son résultat) quitte aussitôt le cache
        setOutcome({
          kind: "awaiting",
          data: {
            invitationId: data.invitation_id,
            organizationName: data.organization_name,
            role: data.role,
            confirmationExpiresAt: data.confirmation_expires_at,
            code: data.confirmation_code,
          },
        });
      } else setOutcome({ kind: "joined", data });
      accept.reset();
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
    // Compte inconnu : on recharge le compte, l'aperçu partira ensuite de lui-même
    if (accountUnknown) void refreshUser();
    else void preview.refetch();
  };

  // Après l'acceptation, le nouveau profil doit figurer dans la liste du serveur avant de pouvoir être ouvert
  const joinedId = view.name === "joined" ? view.data.organization_id : null;
  const joinedReady = !!joinedId && contexts.some((c) => c.type === "ORGANIZATION" && c.id === joinedId);
  // Rechargement de `contexts/` attendu jusqu'au bout : un échec, ou une liste sans l'organisation, n'est jamais un chargement infini
  const [contextsReload, setContextsReload] = useState<"idle" | "loading" | "done">("idle");
  const reloadContexts = useCallback(async () => {
    setContextsReload("loading");
    await invalidateContexts(queryClient);
    setContextsReload("done");
  }, [queryClient]);
  useEffect(() => {
    if (joinedId && !joinedReady && contextsReload === "idle") void reloadContexts();
  }, [joinedId, joinedReady, contextsReload, reloadContexts]);
  const joinedFailed = !!joinedId && !joinedReady && (contextsReload === "done" || (contextsReload !== "idle" && contextsError));
  const joinedWaiting = !!joinedId && !joinedReady && !joinedFailed;

  const openOrganization = (organizationId: string) => {
    // Le profil actif ne change qu'à cet appui (l'utilisateur sait sous quelle identité il agit)
    if (!joinedReady) return;
    setActive({ type: "ORGANIZATION", id: organizationId });
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
            {joinedFailed && (
              <div role="alert" className="space-y-2 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm">
                <p>{t("invitation.joined.contextsError")}</p>
                <Button type="button" variant="outline" className="min-h-11 w-full" onClick={() => void reloadContexts()}>
                  {t("invitation.retry")}
                </Button>
              </div>
            )}
            <Button type="button" className="min-h-12 w-full" disabled={!joinedReady} aria-busy={joinedWaiting || undefined} onClick={() => openOrganization(data.organization_id)}>
              {joinedWaiting && <Loader2 className="animate-spin" aria-hidden />}
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
    case "awaiting": {
      const { data } = view;
      content = (
        <section className={cardClass}>
          {heading(t("invitation.awaiting.title", { name: data.organizationName }), <Hourglass className="h-10 w-10 text-primary" aria-hidden />)}
          <p className="mt-3 text-center text-sm text-muted-foreground">{t("invitation.awaiting.body", { role: t(`role.${data.role}`) })}</p>
          <div className="mt-5">
            <ConfirmationCodeDisplay code={data.code} headingId={codeHeadingId} />
          </div>
          <p className="mt-4 text-center text-sm font-semibold">{t("invitation.awaiting.deadline", { date: formatDateTime(data.confirmationExpiresAt) })}</p>
          <Alert className="mt-4">
            <Info className="h-4 w-4" aria-hidden />
            <AlertDescription>{t("invitation.awaiting.noAccess")}</AlertDescription>
          </Alert>
          {!online && <p className="mt-3 text-xs text-muted-foreground">{t("common.offlineAction")}</p>}
          <div className="mt-6 flex flex-col gap-2">
            {profilesButton}
            <Button ref={withdrawButton} type="button" variant="ghost" className="min-h-12 w-full text-destructive hover:text-destructive" disabled={!online} onClick={() => setWithdrawOpen(true)}>
              {t("invitation.awaiting.withdraw")}
            </Button>
          </div>
        </section>
      );
      break;
    }
    case "withdrawn":
      content = (
        <section className={cardClass}>
          {heading(t("invitation.awaiting.withdrawnTitle"), <XCircle className="h-10 w-10 text-muted-foreground" aria-hidden />)}
          <p className="mt-3 text-center text-sm text-muted-foreground">{t("invitation.awaiting.withdrawnBody")}</p>
          <div className="mt-6 flex flex-col gap-2">{homeButton}</div>
        </section>
      );
      break;
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
      // Rôle Administrateur : aucun accès avant la confirmation par code (contrat §7.4.4)
      const pendingConfirmation = data.requires_confirmation === true;
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
            {data.scope && (
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-muted-foreground">{t("invitation.preview.scope")}</dt>
                <dd className="font-semibold">{scopeLabel(data.scope, t)}</dd>
              </div>
            )}
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted-foreground">{t("invitation.preview.validUntil")}</dt>
              <dd className="font-semibold">{formatLongDate(data.expires_at)}</dd>
            </div>
            {data.capabilities && data.capabilities.length > 0 && (
              <div className="space-y-2">
                <dt className="text-muted-foreground">{t("invitation.preview.access")}</dt>
                <dd>
                  <RoleAccessList capabilities={data.capabilities} />
                </dd>
              </div>
            )}
          </dl>
          {data.role === "ADMIN" && <p className="mt-3 text-sm text-muted-foreground">{t("invitation.preview.adminLimits")}</p>}
          <p className="mt-5 text-sm text-muted-foreground">{t(pendingConfirmation ? "invitation.preview.bodyPending" : "invitation.preview.body")}</p>
          {pendingConfirmation && (
            <Alert id={confirmNoteId} className="mt-4">
              <UserCheck className="h-4 w-4" aria-hidden />
              <AlertTitle>{t("invitation.preview.confirmTitle")}</AlertTitle>
              <AlertDescription>
                <p>{t("invitation.preview.confirmBody")}</p>
                <p className="mt-2">{t("invitation.preview.codeNote")}</p>
              </AlertDescription>
            </Alert>
          )}
          {!online && <p className="mt-3 text-xs text-muted-foreground">{t("common.offlineAction")}</p>}
          <div className="mt-5 flex flex-col gap-2">
            <Button
              type="button"
              className="min-h-12 w-full"
              disabled={busy || !online}
              aria-describedby={pendingConfirmation ? confirmNoteId : undefined}
              onClick={() => void onAccept()}
            >
              {accept.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {t(pendingConfirmation ? "invitation.acceptPending" : "invitation.accept")}
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
        case "missing":
          content = errorCard(t("invitation.err.missing.title"), t("invitation.err.missing.body"), homeButton);
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
        case "review":
          content = errorCard(t("invitation.err.review.title"), t("invitation.err.review.body"), profilesButton);
          break;
        case "awaiting":
          content = errorCard(t("invitation.err.awaiting.title"), t("invitation.err.awaiting.body"), profilesButton);
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
        {withdrawOpen && outcome?.kind === "awaiting" && (
          <WithdrawDialog
            invitationId={outcome.data.invitationId}
            organizationName={outcome.data.organizationName}
            online={online}
            onClose={() => {
              setWithdrawOpen(false);
              requestAnimationFrame(() => withdrawButton.current?.focus());
            }}
            onWithdrawn={() => {
              setWithdrawOpen(false);
              // Le code quitte l'état avec l'écran « Demande envoyée »
              setOutcome({ kind: "withdrawn" });
            }}
            onGone={() => setWithdrawOpen(false)}
          />
        )}
      </Suspense>
    </AppShell>
  );
};

export default OrganizationInvitation;
