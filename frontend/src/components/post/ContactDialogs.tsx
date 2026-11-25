import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, MessageSquare, Package, Repeat } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "@/api/client";
import type { Post, Uuid } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { formatPrice } from "@/lib/format";
import { sellerDisplayName } from "@/lib/post";
import { cn } from "@/lib/utils";
import { useMyPosts } from "@/hooks/use-marketplace";
import { reviewKeys } from "@/hooks/use-reviews";
import { apiErrorCode, apiErrorMessage } from "@/lib/errors";
import { featuresKeys } from "@/hooks/use-features";

interface DialogProps {
  post: Post;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Message interne au vendeur : ouvre une conversation liée à l'annonce. */
export function ContactDialog({ post, open, onOpenChange }: DialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (open && !message) setMessage(t("contactDialog.defaultMessage", { title: post.title }));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- préremplissage à l'ouverture uniquement
  }, [open]);

  const send = useMutation({
    mutationFn: () => apiClient.post("interactions/contacts/", { post: post.id, message: message.trim() }),
    onSuccess: () => {
      // Le contact ouvre le droit d'avis (après le délai éventuel) : on relit l'éligibilité
      void queryClient.invalidateQueries({ queryKey: reviewKeys.eligibilityOf(post.id) });
      toast.success(t("contactDialog.sent"));
      setMessage("");
      onOpenChange(false);
    },
    onError: (error) => toast.error(apiErrorMessage(error, t("contactDialog.failed"))),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-primary" aria-hidden /> {t("contactDialog.title", { name: sellerDisplayName(post.seller) })}
          </DialogTitle>
          <DialogDescription>{t("contactDialog.description")}</DialogDescription>
        </DialogHeader>
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="min-h-[140px] rounded-xl"
          aria-label={t("contactDialog.messageLabel")}
          autoFocus
        />
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => send.mutate()} disabled={send.isPending || !message.trim()}>
            {send.isPending && <Loader2 className="animate-spin" aria-hidden />}
            {t("contactDialog.send")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Proposition de troc : l'acheteur choisit une de ses annonces à échanger (CDC 3.3). */
export function ExchangeDialog({ post, open, onOpenChange }: DialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: myPosts = [], isLoading } = useMyPosts(open);
  const [selectedId, setSelectedId] = useState<Uuid | null>(null);
  const [message, setMessage] = useState("");

  const send = useMutation({
    mutationFn: () => {
      // Le back-end ne stocke pas encore l'annonce proposée : elle est indiquée dans le message
      const offered = myPosts.find((p) => p.id === selectedId);
      const text = offered ? t("exchange.offeredPrefix", { title: offered.title, id: offered.id, message: message.trim() }) : message.trim();
      return apiClient.post("interactions/exchanges/", { post: post.id, message: text });
    },
    onSuccess: () => {
      toast.success(t("exchange.proposalSent"));
      setMessage("");
      setSelectedId(null);
      onOpenChange(false);
    },
    onError: (error) => {
      // Troc éteint entre-temps : message dédié (jamais de nouvelle tentative), on referme et on relit la configuration
      if (apiErrorCode(error) === "feature_disabled") {
        toast.error(t("exchange.disabled"));
        onOpenChange(false);
        void queryClient.invalidateQueries({ queryKey: featuresKeys.all });
        return;
      }
      toast.error(apiErrorMessage(error, t("exchange.proposalFailed")));
    },
  });

  // my_posts renvoie aussi les annonces en pause, vendues ou expirées : seules les annonces en ligne se proposent
  const offerable = myPosts.filter((p) => p.id !== post.id && (p.status ?? "ACTIVE") === "ACTIVE");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Repeat className="h-5 w-5 text-primary" aria-hidden /> {t("exchange.propose")}
          </DialogTitle>
          <DialogDescription>{t("exchange.proposeDescription")}</DialogDescription>
        </DialogHeader>

        <div className="-mx-1 min-h-0 flex-1 space-y-2 overflow-y-auto px-1">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-primary" aria-label={t("exchange.loadingMine")} />
            </div>
          ) : offerable.length === 0 ? (
            <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
              <Package className="mx-auto mb-2 h-8 w-8 opacity-40" aria-hidden />
              {t("exchange.nothingToOffer")}
              <Button asChild variant="link" className="mt-1 h-auto p-0">
                <Link to="/create-post">{t("exchange.publish")}</Link>
              </Button>
            </div>
          ) : (
            <div role="radiogroup" aria-label={t("exchange.offeredLabel")} className="grid gap-2">
              {offerable.map((own) => {
                const selected = own.id === selectedId;
                return (
                  <button
                    key={own.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setSelectedId(selected ? null : own.id)}
                    className={cn(
                      "flex items-center gap-3 rounded-xl border p-2.5 text-left transition-colors",
                      selected ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-secondary",
                    )}
                  >
                    <ImageWithFallback src={own.main_image} alt="" wrapperClassName="h-12 w-12 shrink-0 rounded-lg" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">{own.title}</span>
                      <span className="block text-xs text-muted-foreground">{formatPrice(own.price, own.currency)}</span>
                    </span>
                    {selected && (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                        <Check className="h-4 w-4" aria-hidden />
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={t("exchange.placeholder")}
          className="min-h-[100px] rounded-xl"
          aria-label={t("exchange.messageLabel")}
        />

        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => send.mutate()} disabled={send.isPending || !message.trim()}>
            {send.isPending && <Loader2 className="animate-spin" aria-hidden />}
            {t("exchange.send")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
