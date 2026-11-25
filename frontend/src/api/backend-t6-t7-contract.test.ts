import { describe, expect, it } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { AppNotification, ContactSettings } from "@/api/types";
import { conversationBadge, isConversationNotFound, sendMessageErrorMessage } from "@/lib/messages";
import { contactSettingsErrorMessage, isChannelNotAvailable } from "@/lib/contact-settings";
import { describeApiError } from "@/lib/api-errors";
import { contextFilterOptions, filterNotifications } from "@/lib/notifications";
import type { ConversationItem, MessageItem } from "@/hooks/use-messages";
import identity from "./__fixtures__/backend-identity.json";

/**
 * Recette F3 (L0-09, T6 et T7) : réponses réelles du backend (fixtures enregistrées le 24/10/2026) confrontées aux
 * types du front et aux assistants de lecture. Une régression du contrat côté serveur casse ces tests.
 */
const f = identity as unknown as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const errorOf = (name: string) => ({ response: { status: f[name].status, data: f[name].body, headers: {} } });

describe("notifications : context (T6)", () => {
  const list = f.notifications_list as AppNotification[];

  it("null pour une notification personnelle ; {type, id, name} pour un profil d'équipe", () => {
    const personal = list.find((n) => n.context === null);
    const team = list.find((n) => n.context !== null);
    expect(personal).toBeDefined();
    expect(team?.context).toEqual({ type: "ORGANIZATION", id: expect.stringMatching(UUID), name: "Atelier X" });
  });

  it("le filtre par profil propose le profil de l'organisation et isole ses notifications", () => {
    const options = contextFilterOptions(list);
    expect(options.map((o) => o.label)).toEqual(["Tous les profils", "Personnelles", "Organisation Atelier X"]);
    const team = filterNotifications(list, { context: options[2].value });
    expect(team).toHaveLength(1);
    expect(filterNotifications(list, { context: "personal" })).toHaveLength(1);
  });
});

describe("contact par contexte (T7)", () => {
  it("la réponse porte context et available_channels, et aucun numéro de connexion pour une organisation", () => {
    const org = f.contact_settings_organization as ContactSettings;
    expect(org.context).toEqual({ type: "ORGANIZATION", id: expect.stringMatching(UUID) });
    expect(org.available_channels).toEqual(["MESSAGE"]);
    expect(org.login_phone_masked).toBeNull();
    expect(org.can_use_login_phone).toBe(false);
    expect((f.contact_settings_user as ContactSettings).context.type).toBe("USER");
    expect((f.contact_settings_user as ContactSettings).login_phone_masked).toMatch(/\*\*\*/);
  });

  it("interrupteur ouvert : l'organisation peut configurer les trois canaux", () => {
    expect((f.contact_settings_organization_open as ContactSettings).available_channels).toEqual(["MESSAGE", "CALL", "WHATSAPP"]);
  });

  it("channel_not_available : 400 avec erreur de champ et code machine, texte français", () => {
    const body = f.contact_channel_not_available_error.body;
    expect(f.contact_channel_not_available_error.status).toBe(400);
    expect(body.code).toBe("channel_not_available");
    expect(body.channel).toHaveLength(1);
    expect(isChannelNotAvailable(errorOf("contact_channel_not_available_error"))).toBe(true);
    expect(contactSettingsErrorMessage(errorOf("contact_channel_not_available_error"))).toBe(i18n.t("contactSettings.errors.channel_not_available"));
  });

  it("login_phone_not_allowed : 400, texte français dédié", () => {
    expect(f.contact_login_phone_not_allowed_error.body.code).toBe("login_phone_not_allowed");
    expect(contactSettingsErrorMessage(errorOf("contact_login_phone_not_allowed_error"))).toBe(i18n.t("contactSettings.errors.login_phone_not_allowed"));
  });

  it("rôle sans contact.manage_channels : 403 DENY_PERMISSION, texte d'organisation", () => {
    expect(f.contact_settings_organization_forbidden_editor.body.code).toBe("DENY_PERMISSION");
    expect(contactSettingsErrorMessage(errorOf("contact_settings_organization_forbidden_editor"), { inOrganization: true })).toBe(
      i18n.t("errors.deny.PERMISSION.org"),
    );
  });
});

describe("messagerie par contexte (T7)", () => {
  const buyerList = f.conversations_buyer as ConversationItem[];
  const teamList = f.conversations_organization as ConversationItem[];
  const buyerThread = f.messages_buyer as MessageItem[];
  const teamThread = f.messages_organization as MessageItem[];
  const orgId = buyerList[0].seller_context!.id;

  it("seller_context {type, id} ; l'acheteur voit l'organisation, l'équipe voit l'acheteur abrégé", () => {
    expect(buyerList[0].seller_context).toEqual({ type: "ORGANIZATION", id: expect.stringMatching(UUID) });
    expect(buyerList[0].other_participant?.full_name).toBe("Atelier X");
    expect(teamList[0].other_participant?.full_name).toBe("Marie K.");
    expect(teamList[0].other_participant?.photo).toBeNull();
  });

  it("badges : « Organisation » côté acheteur, « Au nom de » côté équipe", () => {
    expect(conversationBadge(buyerList[0], { type: "USER", id: "u", name: "Marie" })).toEqual({ kind: "ORGANIZATION" });
    expect(conversationBadge(teamList[0], { type: "ORGANIZATION", id: orgId, name: "Atelier X" })).toEqual({ kind: "team", name: "Atelier X" });
  });

  it("message de l'équipe : sender = organisation, sender_name = nom de l'organisation, jamais un membre", () => {
    const reply = buyerThread.find((m) => m.sender_context)!;
    expect(reply.sender).toBe(orgId);
    expect(reply.sender_name).toBe("Atelier X");
    expect(reply.sender_context).toEqual({ type: "ORGANIZATION", id: orgId });
    expect(JSON.stringify(f.messages_buyer)).not.toMatch(/Nom owner|owner@example|\+243970000001/);
  });

  it("is_me : vrai pour l'acheteur côté acheteur, et pour toute l'équipe côté organisation", () => {
    expect(buyerThread.map((m) => m.is_me)).toEqual([true, false]);
    expect(teamThread.map((m) => m.is_me)).toEqual([false, true]);
    expect(teamThread[0].sender_name).toBe("Marie K.");
  });

  it("POST messages : le message créé porte les mêmes clés", () => {
    const created = f.message_post_as_organization as MessageItem;
    expect(created.is_me).toBe(true);
    expect(created.sender_name).toBe("Atelier X");
  });

  it("conversation introuvable : réponse uniforme reconnue, texte français", () => {
    expect(f.message_post_unknown_conversation_error.body).toEqual({ conversation: ["Conversation introuvable."] });
    expect(isConversationNotFound(errorOf("message_post_unknown_conversation_error"))).toBe(true);
    expect(sendMessageErrorMessage(errorOf("message_post_unknown_conversation_error"))).toBe(i18n.t("messages.errors.notFound"));
  });

  it("boîte d'organisation refusée à un éditeur : 403 DENY_PERMISSION", () => {
    expect(f.conversations_organization_forbidden_editor.body.code).toBe("DENY_PERMISSION");
  });

  it("organisation suspendue : DENY_SECURITY pour l'acheteur et pour la boîte ; l'équipe reçoit « introuvable »", () => {
    expect(f.message_post_buyer_to_suspended_organization_error.body.code).toBe("DENY_SECURITY");
    expect(sendMessageErrorMessage(errorOf("message_post_buyer_to_suspended_organization_error"))).toBe(i18n.t("errors.deny.SECURITY.action"));
    expect(describeApiError(errorOf("conversations_suspended_organization_error"))).toBe(i18n.t("errors.deny.SECURITY.action"));
    expect(isConversationNotFound(errorOf("message_post_suspended_organization_error"))).toBe(true);
  });
});

describe("profil public vendeur (T5b)", () => {
  it("clés exactes du contrat, sans coordonnée", () => {
    const profile = f.seller_profile_organization;
    expect(Object.keys(profile).sort()).toEqual(
      [
        "active_offers_count", "context_id", "context_type", "description", "display_name", "member_since", "org_type", "photo",
        "seller_rating", "verification_summary", "verified_claims",
      ].sort(),
    );
    expect(profile.context_type).toBe("ORGANIZATION");
    expect(f.seller_profile_not_found_error.status).toBe(404);
  });
});
