import { useQuery } from "@tanstack/react-query";
import apiClient, { unwrapList } from "@/api/client";
import type { Uuid } from "@/api/types";
import { httpStatus, isRateLimited, retryAfterSeconds, shouldRetryQuery } from "@/lib/errors";

export interface ConversationItem {
  id: Uuid;
  other_participant?: { photo?: string | null; full_name?: string } | null;
  post_title?: string | null;
  last_message?: { content: string; created_at: string | Date } | null;
}

export interface MessageItem {
  id: Uuid;
  sender: Uuid;
  /** Nom affiché de l'expéditeur : le nom de l'organisation quand le message vient de son côté, jamais celui du membre (ADR 0006 §9.8). */
  sender_name?: string;
  sender_context?: { type: string; id: Uuid };
  content: string;
  created_at: string;
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
