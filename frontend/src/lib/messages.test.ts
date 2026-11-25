import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import "@/i18n";
import fr from "@/i18n/locales/fr";
import { conversationBadge, filterConversations, isConversationNotFound, participantName, sendMessageErrorMessage } from "./messages";

const failure = (status: number, data: unknown = {}, headers: Record<string, string> = {}) =>
  new AxiosError(`HTTP ${status}`, String(status), undefined, null, { status, data, headers } as unknown as AxiosResponse);

const ORG_ID = "11111111-1111-4111-8111-111111111111";
const orgActive = { type: "ORGANIZATION", id: ORG_ID, name: "Atelier X" };
const personal = { type: "USER", id: "u1", name: "Moi" };

describe("isConversationNotFound", () => {
  it("reconnaît la réponse uniforme du serveur", () => {
    expect(isConversationNotFound(failure(400, { conversation: ["Conversation introuvable."] }))).toBe(true);
  });
  it("ignore les autres erreurs", () => {
    expect(isConversationNotFound(failure(400, { content: ["Trop long."] }))).toBe(false);
    expect(isConversationNotFound(failure(403, { conversation: ["x"] }))).toBe(false);
    expect(isConversationNotFound(new Error("réseau"))).toBe(false);
  });
});

describe("sendMessageErrorMessage", () => {
  it("conversation introuvable : texte français dédié, jamais celui du serveur", () => {
    expect(sendMessageErrorMessage(failure(400, { conversation: ["Conversation introuvable."] }))).toBe(fr.messages.errors.notFound);
  });

  it("organisation suspendue (DENY_SECURITY) ou archivée (DENY_OBJECT_STATE) : refus clair en français", () => {
    const suspended = failure(403, { detail: "Cette organisation est suspendue.", code: "DENY_SECURITY" });
    const archived = failure(403, { detail: "Archivée.", code: "DENY_OBJECT_STATE" });
    expect(sendMessageErrorMessage(suspended)).toBe(fr.errors.deny.SECURITY.action);
    expect(sendMessageErrorMessage(archived)).toBe(fr.errors.deny.OBJECT_STATE.action);
  });

  it("rôle insuffisant dans une organisation : texte « demandez à un administrateur principal »", () => {
    expect(sendMessageErrorMessage(failure(403, { code: "DENY_PERMISSION" }), true)).toBe(fr.errors.deny.PERMISSION.org);
  });

  it("limite de débit : délai annoncé ; réseau coupé : message réseau", () => {
    expect(sendMessageErrorMessage(failure(429, {}, { "retry-after": "12" }))).toContain("12 secondes");
    expect(sendMessageErrorMessage(new AxiosError("Network Error"))).toBe(fr.errors.network);
  });

  it("erreur inconnue sans détail : repli français", () => {
    expect(sendMessageErrorMessage(failure(400, {}))).toBe(fr.messages.errors.sendFailed);
  });
});

describe("conversationBadge", () => {
  const orgConversation = { seller_context: { type: "ORGANIZATION" as const, id: ORG_ID } };

  it("équipe : « Au nom de » l'organisation active", () => {
    expect(conversationBadge(orgConversation, orgActive)).toEqual({ kind: "team", name: "Atelier X" });
  });

  it("acheteur : « Organisation » (le nom est déjà celui de l'interlocuteur)", () => {
    expect(conversationBadge(orgConversation, personal)).toEqual({ kind: "ORGANIZATION" });
  });

  it("autre organisation active que celle de la conversation : pas « Au nom de »", () => {
    expect(conversationBadge(orgConversation, { ...orgActive, id: "autre" })).toEqual({ kind: "ORGANIZATION" });
  });

  it("prestataire : badge Prestataire ; conversation personnelle ou ancienne : aucun badge", () => {
    expect(conversationBadge({ seller_context: { type: "PROVIDER", id: "p1" } }, personal)).toEqual({ kind: "PROVIDER" });
    expect(conversationBadge({ seller_context: { type: "PROVIDER", id: "p1" } }, { type: "PROVIDER", id: "p1", name: "Marie" })).toBeNull();
    expect(conversationBadge({ seller_context: { type: "PROVIDER", id: "p1" } }, { type: "PROVIDER", id: "p2", name: "Autre" })).toEqual({ kind: "PROVIDER" });
    expect(conversationBadge({ seller_context: { type: "USER", id: "u2" } }, personal)).toBeNull();
    expect(conversationBadge({ seller_context: null }, personal)).toBeNull();
    expect(conversationBadge({}, personal)).toBeNull();
  });
});

describe("participantName et filterConversations", () => {
  const items = [
    { other_participant: { full_name: "Atelier X" }, post_title: "Canapé en cuir" },
    { other_participant: { full_name: "Marie K." }, post_title: "Téléviseur" },
    { other_participant: null, post_title: "Vélo" },
  ];

  it("interlocuteur supprimé : « Utilisateur supprimé »", () => {
    expect(participantName(items[2])).toBe("Utilisateur supprimé");
    expect(participantName(items[0])).toBe("Atelier X");
  });

  it("recherche par nom ou titre, sans accent ni casse", () => {
    expect(filterConversations(items, "marie")).toEqual([items[1]]);
    expect(filterConversations(items, "TELEVISEUR")).toEqual([items[1]]);
    expect(filterConversations(items, "velo")).toEqual([items[2]]);
    expect(filterConversations(items, "  ")).toEqual(items);
    expect(filterConversations(items, "zzz")).toEqual([]);
  });
});
