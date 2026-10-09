import { MessageSquare, Phone } from "lucide-react";
import type { Post } from "@/api/types";
import { Button } from "@/components/ui/button";
import { telLink, whatsappLink } from "@/lib/contact";
import { cn } from "@/lib/utils";

/** Icône WhatsApp (absente de Lucide). */
export const WhatsAppIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
    <path d="M17.47 14.38c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.64.07-.3-.15-1.26-.46-2.4-1.48-.89-.79-1.49-1.77-1.66-2.07-.17-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.48 0 1.46 1.07 2.88 1.21 3.08.15.2 2.1 3.2 5.08 4.49.71.31 1.26.49 1.7.63.71.23 1.36.2 1.87.12.57-.08 1.76-.72 2-1.41.25-.7.25-1.29.18-1.41-.08-.12-.27-.2-.57-.35zM12.05 21.5h-.01a9.4 9.4 0 0 1-4.8-1.32l-.34-.2-3.56.93.95-3.47-.22-.36a9.4 9.4 0 0 1-1.44-5.01c0-5.2 4.24-9.43 9.45-9.43 2.52 0 4.89.98 6.67 2.77a9.36 9.36 0 0 1 2.76 6.67c0 5.2-4.24 9.43-9.46 9.43zm8.04-17.47A11.3 11.3 0 0 0 12.05.7C5.8.7.7 5.78.7 12.03c0 2 .52 3.95 1.52 5.66L.6 23.3l5.74-1.5a11.3 11.3 0 0 0 5.7 1.45h.01c6.26 0 11.35-5.08 11.35-11.33 0-3.03-1.18-5.87-3.32-8.01z" />
  </svg>
);

export function whatsappMessage(post: Post) {
  return `Bonjour, je suis intéressé(e) par votre annonce « ${post.title} » sur Connecte+ : ${window.location.origin}/post/${post.id}`;
}

interface ContactActionsProps {
  post: Post;
  onMessage: () => void;
  /** « stack » : boutons empilés (panneau vendeur) ; « bar » : barre compacte mobile. */
  layout?: "stack" | "bar";
  className?: string;
}

/**
 * Contact du vendeur (CDC 3.5, P1) : appel ou WhatsApp quand le numéro est visible,
 * message interne sinon ou en complément.
 */
export function ContactActions({ post, onMessage, layout = "stack", className }: ContactActionsProps) {
  const phone = post.seller?.phone;
  const call = telLink(phone);
  const whatsapp = whatsappLink(phone, whatsappMessage(post));

  if (layout === "bar") {
    return (
      <div className={cn("flex gap-2", className)}>
        <Button variant="outline" size="icon" className="h-12 w-12 shrink-0 rounded-xl" onClick={onMessage} aria-label="Envoyer un message">
          <MessageSquare className="!h-5 !w-5" />
        </Button>
        {call && (
          <Button asChild variant="outline" size="icon" className="h-12 w-12 shrink-0 rounded-xl">
            <a href={call} aria-label="Appeler le vendeur">
              <Phone className="!h-5 !w-5" />
            </a>
          </Button>
        )}
        {whatsapp ? (
          <Button asChild className="h-12 flex-1 rounded-xl bg-whatsapp text-white hover:bg-whatsapp/90">
            <a href={whatsapp} target="_blank" rel="noopener noreferrer">
              <WhatsAppIcon className="!h-5 !w-5" /> WhatsApp
            </a>
          </Button>
        ) : (
          <Button className="h-12 flex-1 rounded-xl" onClick={onMessage}>
            <MessageSquare aria-hidden /> Contacter
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className={cn("grid gap-2", className)}>
      {whatsapp && (
        <Button asChild size="lg" className="bg-whatsapp text-white hover:bg-whatsapp/90">
          <a href={whatsapp} target="_blank" rel="noopener noreferrer">
            <WhatsAppIcon className="!h-5 !w-5" /> Écrire sur WhatsApp
          </a>
        </Button>
      )}
      {call && (
        <Button asChild size="lg" variant="outline">
          <a href={call}>
            <Phone aria-hidden /> Appeler
          </a>
        </Button>
      )}
      <Button size="lg" variant={whatsapp || call ? "ghost" : "default"} onClick={onMessage}>
        <MessageSquare aria-hidden /> Envoyer un message
      </Button>
    </div>
  );
}
