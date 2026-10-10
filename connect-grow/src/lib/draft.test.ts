import { beforeEach, describe, expect, it } from "vitest";
import { clearDraft, readDraft, writeDraft } from "./draft";
import { POST_DRAFT_KEY } from "./tokens";

describe("brouillon d'annonce", () => {
  beforeEach(() => localStorage.clear());

  it("restitue le brouillon de son propriétaire", () => {
    writeDraft("u-1", { title: "Vélo" });
    expect(readDraft("u-1")).toEqual({ title: "Vélo" });
  });

  it("ignore le brouillon d'un autre utilisateur", () => {
    writeDraft("u-1", { title: "Vélo" });
    expect(readDraft("u-2")).toBeNull();
  });

  it("ignore un ancien brouillon sans propriétaire et un utilisateur inconnu", () => {
    localStorage.setItem(POST_DRAFT_KEY, JSON.stringify({ title: "Vélo" }));
    expect(readDraft("u-1")).toBeNull();
    writeDraft(undefined, { title: "X" });
    expect(readDraft(undefined)).toBeNull();
  });

  it("l'efface", () => {
    writeDraft("u-1", { title: "Vélo" });
    clearDraft();
    expect(readDraft("u-1")).toBeNull();
  });
});
