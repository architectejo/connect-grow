import { useState } from "react";
import { MessageSquare, Phone } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ContactChannel, RevealChannel, SellerContextType, Uuid } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ContactRevealDialog } from "@/components/post/ContactRevealDialog";
import { cn } from "@/lib/utils";

interface ContactActionsProps {
  offerId: Uuid;
  sellerName: string;
  /** Moyens acceptés par le vendeur (`allowed_channels`). Un moyen absent n'est pas affiché. */
  allowedChannels: ContactChannel[];
  /**
   * Type du vendeur : pour une organisation, le client suit `allowed_channels` du serveur (qui tient compte de
   * l'interrupteur des canaux téléphoniques) et ne déduit rien du type. Sert seulement à choisir le texte explicatif.
   */
  sellerType?: SellerContextType;
  onMessage: () => void;
  /** « stack » : boutons empilés (panneau vendeur) ; « bar » : barre compacte mobile. */
  layout?: "stack" | "bar";
  className?: string;
}

/** Icône WhatsApp (absente de lucide-react) : bulle de conversation avec combiné. */
function WhatsAppIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("h-4 w-4", className)}
      aria-hidden
    >
      <path d="M3 21l1.65-4.9A8.5 8.5 0 1 1 8 19.4L3 21z" />
      <path d="M9 9.5c0 3 2.5 5.5 5.5 5.5l1-1.5-2-1-.8.8a3.5 3.5 0 0 1-1.5-1.5l.8-.8-1-2L9 9.5z" />
    </svg>
  );
}

/**
 * Contact du vendeur selon ses consentements. Aucun numéro ni lien de téléphone ou de WhatsApp n'est dans la page :
 * le numéro n'arrive qu'après un clic, dans la boîte de dialogue (règle 10).
 */
export function ContactActions({ offerId, sellerName, allowedChannels, sellerType, onMessage, layout = "stack", className }: ContactActionsProps) {
  const { t } = useTranslation();
  const [channel, setChannel] = useState<RevealChannel | null>(null);
  const canMessage = allowedChannels.includes("MESSAGE");
  const canCall = allowedChannels.includes("CALL");
  const canWhatsapp = allowedChannels.includes("WHATSAPP");

  if (!canMessage && !canCall && !canWhatsapp) {
    // Aucun bouton de contact, avec une explication (organisation sans canal : `seller_contact_unavailable`)
    return (
      <p className={cn("text-center text-sm text-muted-foreground", className)}>
        {sellerType === "ORGANIZATION" ? t("contact.orgUnavailable") : t("post.contact.none")}
      </p>
    );
  }
  const orgMessageOnly = sellerType === "ORGANIZATION" && canMessage && !canCall && !canWhatsapp;
  const note = orgMessageOnly ? <p className="text-center text-xs text-muted-foreground">{t("contact.orgMessageOnly")}</p> : null;

  const dialog = (
    <ContactRevealDialog
      offerId={offerId}
      sellerName={sellerName}
      channel={channel}
      onClose={() => setChannel(null)}
      onMessage={canMessage ? onMessage : undefined}
    />
  );

  if (layout === "bar") {
    return (
      <div className={cn("flex flex-wrap gap-2", className)}>
        {canMessage && (
          <Button className="h-12 flex-1 rounded-xl" onClick={onMessage}>
            <MessageSquare aria-hidden /> {t("post.contact.sendMessageShort")}
          </Button>
        )}
        {canCall && (
          <Button
            variant="outline"
            className={cn("h-12 rounded-xl px-4", !canMessage && "flex-1")}
            aria-label={t("post.contact.callLabel")}
            onClick={() => setChannel("CALL")}
          >
            <Phone aria-hidden />
          </Button>
        )}
        {canWhatsapp && (
          <Button
            variant="outline"
            className={cn("h-12 rounded-xl px-4", !canMessage && !canCall && "flex-1")}
            aria-label={t("post.contact.whatsappLabel")}
            onClick={() => setChannel("WHATSAPP")}
          >
            <WhatsAppIcon className="h-5 w-5" />
          </Button>
        )}
        {dialog}
        {note && <div className="w-full">{note}</div>}
      </div>
    );
  }

  return (
    <div className={cn("grid gap-2", className)}>
      {canMessage && (
        <Button size="lg" onClick={onMessage}>
          <MessageSquare aria-hidden /> {t("post.contact.sendMessage")}
        </Button>
      )}
      {canCall && (
        <Button size="lg" variant="outline" onClick={() => setChannel("CALL")}>
          <Phone aria-hidden /> {t("post.contact.call")}
        </Button>
      )}
      {canWhatsapp && (
        <Button size="lg" variant="outline" onClick={() => setChannel("WHATSAPP")}>
          <WhatsAppIcon /> {t("post.contact.whatsapp")}
        </Button>
      )}
      {dialog}
      {note}
    </div>
  );
}
