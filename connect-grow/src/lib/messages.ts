import type { ConversationItem } from "@/hooks/use-messages";
import i18n from "@/i18n";
import { describeApiError } from "@/lib/api-errors";
import { httpStatus } from "@/lib/errors";

interface ActiveProfile {
  type: string;
  id: string;
  name: string;
}

/** Réponse uniforme du serveur pour une conversation inconnue, mal formée ou interdite (aucun oracle d'existence). */
export function isConversationNotFound(error: unknown): boolean {
  if (httpStatus(error) !== 400) return false;
  const data = (error as { response?: { data?: unknown } }).response?.data;
  return typeof data === "object" && data !== null && Array.isArray((data as { conversation?: unknown }).conversation);
}

/** Texte français d'un échec d'envoi : conversation disparue, refus `DENY_*` (organisation suspendue, rôle), limite, réseau. */
export function sendMessageErrorMessage(error: unknown, inOrganization = false): string {
  if (isConversationNotFound(error)) return i18n.t("messages.errors.notFound");
  return describeApiError(error, { inOrganization, fallback: i18n.t("messages.errors.sendFailed") });
}

export type ConversationBadge = { kind: "team"; name: string } | { kind: "ORGANIZATION" | "PROVIDER" } | null;

/**
 * Badge d'une conversation. Côté équipe (profil actif = l'organisation de la conversation) : « Au nom de X ».
 * Côté acheteur d'une organisation ou d'un prestataire : « Organisation » / « Prestataire », le nom étant déjà celui
 * de l'interlocuteur. Conversation personnelle : aucun badge.
 */
export function conversationBadge(conversation: Pick<ConversationItem, "seller_context">, active: ActiveProfile): ConversationBadge {
  const seller = conversation.seller_context;
  if (!seller || seller.type === "USER") return null;
  if (seller.type === "ORGANIZATION" && active.type === "ORGANIZATION" && active.id === seller.id) return { kind: "team", name: active.name };
  // Le prestataire lui-même n'a pas besoin d'être informé qu'il parle à un prestataire
  if (seller.type === "PROVIDER" && active.type === "PROVIDER" && active.id === seller.id) return null;
  return { kind: seller.type };
}

/** Nom de l'interlocuteur : celui du serveur, ou « Utilisateur supprimé » quand il n'y en a plus. */
export const participantName = (conversation: Pick<ConversationItem, "other_participant">): string =>
  conversation.other_participant?.full_name || i18n.t("messages.deletedUser");

/** Filtre local de la liste (nom de l'interlocuteur ou titre de l'offre), sans accent ni casse. */
export function filterConversations<T extends Pick<ConversationItem, "other_participant" | "post_title">>(items: T[], query: string): T[] {
  const fold = (value: string) => value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const needle = fold(query.trim());
  if (!needle) return items;
  return items.filter((item) => fold(`${item.other_participant?.full_name ?? ""} ${item.post_title ?? ""}`).includes(needle));
}
