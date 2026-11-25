import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type {
  ChangeMemberRoleBody,
  CreatedInvitation,
  CreateInvitationBody,
  InvitationAccepted,
  InvitationPreview,
  OrganizationInvitation,
  OrganizationMember,
  Paginated,
  TransferOwnershipBody,
  TransferOwnershipResult,
  Uuid,
} from "@/api/types";
import { useAuth } from "@/contexts/AuthContext";
import { invalidateContexts } from "@/hooks/use-contexts";
import { organizationKeys } from "@/hooks/use-organizations";
import { getApiErrorCode } from "@/lib/api-errors";
import { shouldRetryQuery } from "@/lib/errors";
import { InvitationTokenMissingError, bindInvitationToken, clearInvitationToken, readInvitationToken } from "@/lib/invitation-token";

// Équipe d'une organisation (L1-01, contrat `docs/specs/L1-01-contrat-api.md` §1). Les réponses sont `private, no-store`
// et contiennent des noms de personnes : elles ne vivent qu'en mémoire de l'onglet (aucun cache persistant, service
// worker en réseau seul : voir lib/cache-rules.ts). Le mot de passe de ressaisie ne passe que par le corps d'un PATCH/POST :
// jamais dans une URL, une clé de requête, un stockage ni un journal.

export const teamKeys = {
  members: (orgId: Uuid) => [...organizationKeys.all, "members", orgId] as const,
  /** Préfixe réservé à l'onglet Invitations (F2) : invalidé aussi après un retrait (ses invitations sont révoquées). */
  invitations: (orgId: Uuid) => [...organizationKeys.all, "invitations", orgId] as const,
};

const base = (orgId: Uuid) => `accounts/organizations/${orgId}/`;
export const membersUrl = (orgId: Uuid) => `${base(orgId)}members/`;
export const memberUrl = (orgId: Uuid, membershipId: Uuid) => `${membersUrl(orgId)}${membershipId}/`;
export const transferUrl = (orgId: Uuid) => `${base(orgId)}transfer-ownership/`;
export const invitationsUrl = (orgId: Uuid) => `${base(orgId)}invitations/`;
export const invitationUrl = (orgId: Uuid, invitationId: Uuid) => `${invitationsUrl(orgId)}${invitationId}/`;
/** Échange du jeton : le jeton voyage dans le corps du POST, jamais dans ces URL. */
export const invitationExchangeUrl = (action: "preview" | "accept" | "decline") => `accounts/organization-invitations/${action}/`;

/** Clé de l'aperçu d'invitation : volontairement SANS le jeton (une clé de requête n'est jamais un secret). */
export const INVITATION_PREVIEW_KEY = ["org-invitation-preview"] as const;

/** Membres actifs, 20 par page (« Voir plus »). Jamais de relance automatique d'un 429, 5xx ou réseau coupé. */
export function useMembers(orgId: Uuid | undefined) {
  const { isAuthenticated } = useAuth();
  return useInfiniteQuery({
    queryKey: teamKeys.members(orgId ?? ""),
    queryFn: async ({ pageParam }) =>
      (await apiClient.get<Paginated<OrganizationMember>>(membersUrl(orgId as Uuid), { params: pageParam > 1 ? { page: pageParam } : undefined })).data,
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
    enabled: isAuthenticated && !!orgId,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: shouldRetryQuery,
    select: (data) => {
      // Une ligne peut changer de page entre deux chargements : on dédoublonne par identifiant d'appartenance
      const seen = new Set<Uuid>();
      const members = data.pages.flatMap((page) => page.results).filter((m) => !seen.has(m.membership_id) && !!seen.add(m.membership_id));
      return { members, count: data.pages[0]?.count ?? members.length };
    },
  });
}

/** Après un refus du serveur : l'écran se réaligne sur la réalité (liste, rôle de l'acteur). */
function refreshAfterRefusal(queryClient: QueryClient, orgId: Uuid, error: unknown) {
  const code = getApiErrorCode(error);
  if (code === "member_not_found") {
    void queryClient.invalidateQueries({ queryKey: teamKeys.members(orgId) });
  } else if (code === "invitation_not_pending" || code === "invitation_not_found") {
    void queryClient.invalidateQueries({ queryKey: teamKeys.invitations(orgId) });
  } else if (code === "DENY_PERMISSION" || code === "DENY_RELATION" || code === "DENY_OBJECT_STATE" || code === "DENY_SECURITY") {
    void queryClient.invalidateQueries({ queryKey: teamKeys.members(orgId) });
    void queryClient.invalidateQueries({ queryKey: organizationKeys.internal(orgId) });
  }
}

/**
 * Changer le rôle d'un membre. `gcTime: 0` : la mutation (et le mot de passe qu'elle porte) quitte le cache dès
 * qu'aucun composant ne l'observe. Aucune relance automatique, aucune file hors ligne.
 */
export function useChangeMemberRole(orgId: Uuid) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ membershipId, body }: { membershipId: Uuid; body: ChangeMemberRoleBody }) =>
      (await apiClient.patch<OrganizationMember>(memberUrl(orgId, membershipId), body)).data,
    gcTime: 0,
    retry: false,
    // Rechargement en arrière-plan : la mutation n'attend pas la liste
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.members(orgId) });
    },
    onError: (error) => refreshAfterRefusal(queryClient, orgId, error),
  });
}

/** Retirer un membre (204). Ses invitations en attente sont révoquées par le serveur : la liste des invitations est rechargée. */
export function useRemoveMember(orgId: Uuid) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (membershipId: Uuid) => {
      await apiClient.delete(memberUrl(orgId, membershipId));
    },
    gcTime: 0,
    retry: false,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.members(orgId) });
      void queryClient.invalidateQueries({ queryKey: teamKeys.invitations(orgId) });
    },
    onError: (error) => refreshAfterRefusal(queryClient, orgId, error),
  });
}

/**
 * Transfert d'administration principale. Le rôle de l'acteur change : détail de l'organisation (`my_role`, capacités), liste des profils
 * (rôle mémorisé du profil actif) et liste des membres sont rechargés.
 */
export function useTransferOwnership(orgId: Uuid) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TransferOwnershipBody) => (await apiClient.post<TransferOwnershipResult>(transferUrl(orgId), body)).data,
    gcTime: 0,
    retry: false,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.members(orgId) });
      void queryClient.invalidateQueries({ queryKey: organizationKeys.internal(orgId) });
      void invalidateContexts(queryClient);
    },
    onError: (error) => refreshAfterRefusal(queryClient, orgId, error),
  });
}

/**
 * Invitations en attente (onglet Invitations, 20 par page). `enabled` : la requête ne part qu'à l'ouverture de l'onglet.
 * Aucune donnée de jeton : la réponse n'en contient jamais.
 */
export function useInvitations(orgId: Uuid | undefined, enabled = true) {
  const { isAuthenticated } = useAuth();
  return useInfiniteQuery({
    queryKey: teamKeys.invitations(orgId ?? ""),
    queryFn: async ({ pageParam }) =>
      (
        await apiClient.get<Paginated<OrganizationInvitation>>(invitationsUrl(orgId as Uuid), {
          params: { status: "PENDING", ...(pageParam > 1 ? { page: pageParam } : {}) },
        })
      ).data,
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
    enabled: enabled && isAuthenticated && !!orgId,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: shouldRetryQuery,
    select: (data) => {
      const seen = new Set<Uuid>();
      const invitations = data.pages.flatMap((page) => page.results).filter((i) => !seen.has(i.invitation_id) && !!seen.add(i.invitation_id));
      return { invitations, count: data.pages[0]?.count ?? invitations.length };
    },
  });
}

/**
 * Créer une invitation. `gcTime: 0` : le résultat (qui porte `link_token`, relisible nulle part ailleurs) quitte le cache
 * de mutations dès que le dialogue se démonte ; il n'entre jamais dans le cache de requêtes. Pas de relance automatique
 * (deux invitations par erreur).
 */
export function useCreateInvitation(orgId: Uuid) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: CreateInvitationBody) => (await apiClient.post<CreatedInvitation>(invitationsUrl(orgId), body)).data,
    gcTime: 0,
    retry: false,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.invitations(orgId) });
    },
    onError: (error) => refreshAfterRefusal(queryClient, orgId, error),
  });
}

/** Annuler une invitation en attente (204) : le lien devient inutilisable. */
export function useRevokeInvitation(orgId: Uuid) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (invitationId: Uuid) => {
      await apiClient.delete(invitationUrl(orgId, invitationId));
    },
    gcTime: 0,
    retry: false,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.invitations(orgId) });
    },
    onError: (error) => refreshAfterRefusal(queryClient, orgId, error),
  });
}

/**
 * Le jeton est relu dans `sessionStorage` au moment de l'appel : il n'est ni une variable de mutation, ni une clé de requête.
 * Lu pour le compte connecté : un jeton lié à un autre compte, ou de plus de 60 minutes, est effacé et l'appel n'a pas lieu.
 */
function tokenBody(accountId: string | undefined): { token: string } {
  // Sans compte identifié, le jeton ne peut être lié à personne : aucun appel
  if (!accountId) throw new InvitationTokenMissingError();
  const token = readInvitationToken(accountId);
  if (!token) throw new InvitationTokenMissingError();
  return { token };
}

/**
 * Aperçu (POST, sans effet de bord) : `useQuery` à fonction POST, clé sans le jeton, jamais conservé (`gcTime: 0`),
 * jamais relancé sur un 4xx. `enabled` seulement pour un visiteur connecté qui détient un jeton. Un aperçu réussi lie
 * le jeton au compte connecté (un autre compte ne pourra plus s'en servir dans cet onglet).
 */
export function useInvitationPreview(enabled: boolean) {
  const { user } = useAuth();
  const accountId = user?.id;
  return useQuery({
    queryKey: INVITATION_PREVIEW_KEY,
    queryFn: async () => {
      const data = (await apiClient.post<InvitationPreview>(invitationExchangeUrl("preview"), tokenBody(accountId))).data;
      if (accountId) bindInvitationToken(accountId);
      return data;
    },
    enabled,
    staleTime: 0,
    gcTime: 0,
    // Sans jeton utilisable, rien n'est parti au réseau : un nouvel essai ne changerait rien
    retry: (count, error) => !(error instanceof InvitationTokenMissingError) && shouldRetryQuery(count, error),
    refetchOnWindowFocus: false,
  });
}

/**
 * Accepter : le profil actif ne change pas (bouton « Ouvrir l'organisation »). Le jeton est effacé au succès.
 * La liste des profils est rechargée AVANT la résolution : le nouveau profil est sélectionnable dès l'écran de succès.
 */
export function useAcceptInvitation() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const accountId = user?.id;
  return useMutation({
    mutationFn: async () => (await apiClient.post<InvitationAccepted>(invitationExchangeUrl("accept"), tokenBody(accountId))).data,
    gcTime: 0,
    retry: false,
    onSuccess: () => {
      clearInvitationToken();
      return invalidateContexts(queryClient);
    },
  });
}

/** Refuser (204) : le jeton est effacé au succès. */
export function useDeclineInvitation() {
  const { user } = useAuth();
  const accountId = user?.id;
  return useMutation({
    mutationFn: async () => {
      await apiClient.post(invitationExchangeUrl("decline"), tokenBody(accountId));
    },
    gcTime: 0,
    retry: false,
    onSuccess: () => clearInvitationToken(),
  });
}
