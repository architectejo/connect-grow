import { useQuery } from "@tanstack/react-query";
import apiClient, { unwrapList } from "@/api/client";
import type { ContextType, Uuid } from "@/api/types";
import { httpStatus, isRateLimited, retryAfterSeconds, shouldRetryQuery } from "@/lib/errors";

/** Profil vendeur d'une conversation (ADR 0006 §9.8). `name` n'est pas renvoyé par la liste : le nom affiché est `other_participant`. */
export interface ConversationSellerContext {
  type: ContextType;
  id: Uuid;
  name?: string;
}

export interface ConversationItem {
  id: Uuid;
  /** Côté acheteur d'une conversation d'organisation : l'organisation (nom, jamais un membre) ; côté équipe : l'acheteur, nom abrégé. */
  other_participant?: { id?: Uuid; photo?: string | null; full_name?: string } | null;
  post_title?: string | null;
  /** null : conversation personnelle ou ancienne conversation sans profil vendeur. */
  seller_context?: ConversationSellerContext | null;
  /** `sender_id` : l'organisation quand le message vient de son équipe, jamais un membre. */
  last_message?: { content: string; created_at: string | Date; is_read?: boolean; sender_id?: Uuid } | null;
}

export interface MessageItem {
  id: Uuid;
  conversation?: Uuid;
  /** Identifiant de l'organisation quand le message vient de son équipe, sinon celui du compte (null si supprimé). */
  sender: Uuid | null;
  /** Nom affiché de l'expéditeur : le nom de l'organisation quand le message vient de son côté, jamais celui du membre (ADR 0006 §9.8) ; « Utilisateur supprimé » sans auteur. */
  sender_name?: string;
  sender_context?: { type: ContextType; id: Uuid } | null;
  content: string;
  is_read?: boolean;
  created_at: string;
  /** Fourni par le serveur : le message est « de mon côté » (moi, ou mon organisation). */
  is_me: boolean;
}

export const messageKeys = {
  conversations: ["messages", "conversations"] as const,
  thread: (conversationId: Uuid) => ["messages", "thread", conversationId] as const,
};

export const MESSAGES_POLL_MS = 5_000;
const DEFAULT_PAUSE_MS = 30_000;

/**
 * Délai avant la prochaine actualisation de la conversation (false = arrêt).
 * - 401, 403, 404 : la conversation n'est plus accessible, on arrête d'interroger.
 * - 429 : pause pendant Retry-After (30 s par défaut), puis reprise.
 * Le reste du temps : toutes les 5 s. React Query suspend déjà les requêtes onglet masqué
 * (`refetchIntervalInBackground: false`).
 */
export function messagesRefetchInterval(error: unknown): number | false {
  const status = httpStatus(error);
  if (status === 401 || status === 403 || status === 404) return false;
  if (isRateLimited(error)) return Math.max(MESSAGES_POLL_MS, (retryAfterSeconds(error) ?? DEFAULT_PAUSE_MS / 1000) * 1000);
  return MESSAGES_POLL_MS;
}

/**
 * Conversations de l'utilisateur. L'API renvoie un tableau tant qu'on n'envoie ni `?page` ni `?page_size`
 * (OptionalPagination) et ce front n'en envoie jamais ; unwrapList reste tolérant à l'enveloppe paginée.
 */
export function useConversations(enabled = true) {
  return useQuery({
    queryKey: messageKeys.conversations,
    queryFn: async () => unwrapList<ConversationItem>((await apiClient.get("interactions/conversations/")).data),
    enabled,
    retry: shouldRetryQuery,
  });
}

/** Messages d'une conversation, actualisés périodiquement (même règle de pagination que les conversations). */
export function useConversationMessages(conversationId?: Uuid) {
  const query = useQuery({
    queryKey: messageKeys.thread(conversationId ?? ""),
    queryFn: async () =>
      unwrapList<MessageItem>((await apiClient.get("interactions/messages/", { params: { conversation: conversationId } })).data),
    enabled: !!conversationId,
    retry: shouldRetryQuery,
    refetchInterval: (q) => messagesRefetchInterval(q.state.error),
    refetchIntervalInBackground: false,
  });
  return { ...query, isPaused: isRateLimited(query.error) };
}
