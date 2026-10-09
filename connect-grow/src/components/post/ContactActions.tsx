import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Post } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ContactActionsProps {
  post: Post;
  onMessage: () => void;
  /** « stack » : boutons empilés (panneau vendeur) ; « bar » : barre compacte mobile. */
  layout?: "stack" | "bar";
  className?: string;
}

/**
 * Contact du vendeur : seul canal, le message interne (règle 10 : le numéro n'est jamais public).
 * Le contact par téléphone viendra avec le consentement du vendeur (L0-10a-b).
 */
export function ContactActions({ onMessage, layout = "stack", className }: ContactActionsProps) {
  const { t } = useTranslation();

  if (layout === "bar") {
    return (
      <div className={cn("flex gap-2", className)}>
        <Button className="h-12 flex-1 rounded-xl" onClick={onMessage}>
          <MessageSquare aria-hidden /> {t("post.contact.sendMessageShort")}
        </Button>
      </div>
    );
  }

  return (
    <div className={cn("grid gap-2", className)}>
      <Button size="lg" onClick={onMessage}>
        <MessageSquare aria-hidden /> {t("post.contact.sendMessage")}
      </Button>
      <p className="text-center text-xs text-muted-foreground">{t("post.contact.phoneSoon")}</p>
    </div>
  );
}
