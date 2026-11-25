import { useEffect, useRef } from "react";
import { AlwaysPersonalNote } from "@/components/profiles/AlwaysPersonalNote";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ExternalLink, Loader2, MessageSquare, Phone } from "lucide-react";
import type { RevealChannel, Uuid } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { useRevealContact } from "@/hooks/use-contact-reveal";
import { loginPath } from "@/lib/auth-paths";
import { revealErrorInfo, revealLink } from "@/lib/contact-reveal";

interface ContactRevealDialogProps {
  offerId: Uuid;
  sellerName: string;
  /** Canal demandé ; null = fermé. */
  channel: RevealChannel | null;
  onClose: () => void;
  /** Repli proposé quand le moyen est indisponible ou limité : le message interne (si le vendeur l'accepte). */
  onMessage?: () => void;
}

/**
 * Révélation du numéro du vendeur (ADR 0005, règle 10). Rien n'est demandé avant le clic sur « Afficher le numéro » :
 * le visiteur est d'abord prévenu que le vendeur sera averti. Le numéro et les liens viennent uniquement de la
 * réponse du serveur, vivent dans l'état de la mutation et disparaissent à la fermeture.
 */
export function ContactRevealDialog({ offerId, sellerName, channel, onClose, onMessage }: ContactRevealDialogProps) {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const reveal = useRevealContact();
  const resultRef = useRef<HTMLAnchorElement>(null);
  const { reset } = reveal;

  // Fermeture ou changement de canal : le numéro précédent est effacé de la mémoire.
  useEffect(() => {
    reset();
  }, [channel, reset]);

  const result = reveal.data;
  const link = result ? revealLink(result.channel, result) : null;
  useEffect(() => {
    if (link) resultRef.current?.focus();
  }, [link]);

  if (!channel) return null;

  const error = reveal.isError ? revealErrorInfo(reveal.error) : null;
  const needsLogin = !isAuthenticated || error?.kind === "login";
  const canFallbackToMessage = !!onMessage && (error?.kind === "limit" || error?.kind === "unavailable");
  const title = t(channel === "CALL" ? "reveal.callTitle" : "reveal.whatsappTitle", { seller: sellerName });
  const Icon = channel === "CALL" ? Phone : MessageSquare;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon className="h-5 w-5 text-primary" aria-hidden /> {title}
          </DialogTitle>
          <DialogDescription>{t("reveal.description")}</DialogDescription>
        </DialogHeader>

        {needsLogin ? (
          <p className="text-sm">{error ? error.message : t("reveal.loginPrompt")}</p>
        ) : result && link ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t("reveal.numberLabel")}</p>
            <p className="font-display text-2xl font-extrabold tabular-nums" data-testid="revealed-phone">
              {result.phone}
            </p>
            <Button asChild size="lg" className="w-full">
              <a
                ref={resultRef}
                href={link}
                {...(result.channel === "WHATSAPP" ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              >
                {result.channel === "CALL" ? <Phone aria-hidden /> : <ExternalLink aria-hidden />}
                {t(result.channel === "CALL" ? "reveal.callNow" : "reveal.openWhatsapp")}
              </a>
            </Button>
          </div>
        ) : result ? (
          <p className="text-sm text-destructive">{t("reveal.unexpected")}</p>
        ) : (
          <div className="space-y-2 text-sm">
            <p>{t("reveal.notice")}</p>
            {channel === "WHATSAPP" && <p className="text-muted-foreground">{t("reveal.noticeWhatsapp")}</p>}
            <AlwaysPersonalNote />
          </div>
        )}

        {/* Annonce vocale : le résultat est lu sans déplacer le focus */}
        <div role="status" aria-live="polite" className="sr-only">
          {reveal.isPending ? t("reveal.loading") : result ? t("reveal.revealed") : ""}
        </div>
        {error && !needsLogin && (
          <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">
            {error.message}
          </p>
        )}

        <DialogFooter className="gap-2 sm:space-x-0">
          {canFallbackToMessage && (
            <Button
              variant="soft"
              onClick={() => {
                onClose();
                onMessage?.();
              }}
            >
              <MessageSquare aria-hidden /> {t("reveal.writeMessage")}
            </Button>
          )}
          {needsLogin ? (
            <Button asChild>
              <Link to={loginPath(location.pathname)}>{t("reveal.login")}</Link>
            </Button>
          ) : !result && !(error && error.kind !== "retry") ? (
            <Button onClick={() => reveal.mutate({ offer: offerId, channel })} disabled={reveal.isPending}>
              {reveal.isPending && <Loader2 className="animate-spin" aria-hidden />}
              {error ? t("reveal.retry") : t("reveal.show")}
            </Button>
          ) : null}
          <Button variant="ghost" onClick={onClose}>
            {t("reveal.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
