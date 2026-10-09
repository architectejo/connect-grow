import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Check, Loader2, MessageSquare, Package, Repeat } from "lucide-react";
import { toast } from "sonner";
import apiClient from "@/api/client";
import type { Post, Uuid } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { formatPrice } from "@/lib/format";
import { sellerDisplayName } from "@/lib/trust";
import { cn } from "@/lib/utils";
import { useMyPosts } from "@/hooks/use-marketplace";
import { apiErrorMessage } from "@/lib/errors";

interface DialogProps {
  post: Post;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Message interne au vendeur : ouvre une conversation liée à l'annonce. */
export function ContactDialog({ post, open, onOpenChange }: DialogProps) {
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (open && !message) setMessage(`Bonjour, votre annonce « ${post.title} » est-elle toujours disponible ?`);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- préremplissage à l'ouverture uniquement
  }, [open]);

  const send = useMutation({
    mutationFn: () => apiClient.post("interactions/contacts/", { post: post.id, message: message.trim() }),
    onSuccess: () => {
      toast.success("Message envoyé. Retrouvez la conversation dans vos messages.");
      setMessage("");
      onOpenChange(false);
    },
    onError: (error) => toast.error(apiErrorMessage(error, "Le message n'a pas pu être envoyé.")),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-primary" aria-hidden /> Contacter {sellerDisplayName(post.seller)}
          </DialogTitle>
          <DialogDescription>Votre message ouvre une conversation privée à propos de cette annonce.</DialogDescription>
        </DialogHeader>
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="min-h-[140px] rounded-xl"
          aria-label="Votre message"
          autoFocus
        />
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Annuler
          </Button>
          <Button onClick={() => send.mutate()} disabled={send.isPending || !message.trim()}>
            {send.isPending && <Loader2 className="animate-spin" aria-hidden />}
            Envoyer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Proposition de troc : l'acheteur choisit une de ses annonces à échanger (CDC 3.3). */
export function ExchangeDialog({ post, open, onOpenChange }: DialogProps) {
  const { data: myPosts = [], isLoading } = useMyPosts(open);
  const [selectedId, setSelectedId] = useState<Uuid | null>(null);
  const [message, setMessage] = useState("");

  const send = useMutation({
    mutationFn: () => {
      // Le back-end ne stocke pas encore l'annonce proposée : elle est indiquée dans le message
      const offered = myPosts.find((p) => p.id === selectedId);
      const text = offered ? `[Annonce proposée : « ${offered.title} » (n° ${offered.id})] ${message.trim()}` : message.trim();
      return apiClient.post("interactions/exchanges/", { post: post.id, message: text });
    },
    onSuccess: () => {
      toast.success("Proposition d'échange envoyée.");
      setMessage("");
      setSelectedId(null);
      onOpenChange(false);
    },
    onError: (error) => toast.error(apiErrorMessage(error, "La proposition n'a pas pu être envoyée.")),
  });

  // my_posts renvoie aussi les annonces en pause, vendues ou expirées : seules les annonces en ligne se proposent
  const offerable = myPosts.filter((p) => p.id !== post.id && (p.status ?? "ACTIVE") === "ACTIVE");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Repeat className="h-5 w-5 text-primary" aria-hidden /> Proposer un échange
          </DialogTitle>
          <DialogDescription>Choisissez l'annonce que vous proposez en échange, puis précisez votre offre.</DialogDescription>
        </DialogHeader>

        <div className="-mx-1 min-h-0 flex-1 space-y-2 overflow-y-auto px-1">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-primary" aria-label="Chargement de vos annonces" />
            </div>
          ) : offerable.length === 0 ? (
            <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
              <Package className="mx-auto mb-2 h-8 w-8 opacity-40" aria-hidden />
              Vous n'avez pas encore d'annonce à proposer.
              <Button asChild variant="link" className="mt-1 h-auto p-0">
                <Link to="/create-post">Publier une annonce</Link>
              </Button>
            </div>
          ) : (
            <div role="radiogroup" aria-label="Annonce proposée" className="grid gap-2">
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
          placeholder="Ex. : je propose mon téléphone + 20 $ de complément."
          className="min-h-[100px] rounded-xl"
          aria-label="Votre proposition"
        />

        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Annuler
          </Button>
          <Button onClick={() => send.mutate()} disabled={send.isPending || !message.trim()}>
            {send.isPending && <Loader2 className="animate-spin" aria-hidden />}
            Envoyer la proposition
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
