import { beforeEach, describe, expect, it } from "vitest";
import type { AvailableContext } from "@/api/types";
import { clearLegacyNotices, dismissLegacyNotice, isLegacyNoticeDismissed, legacyNoticeKey, migratedOrganizations } from "./legacy-notice";

const ctx = (over: Partial<AvailableContext>): AvailableContext => ({
  type: "ORGANIZATION",
  id: "o1",
  name: "Atelier",
  role: "OWNER",
  org_type: "ENTREPRISE",
  photo: null,
  capabilities: [],
  migrated_from_business: false,
  status: "ACTIVE",
  ...over,
});

describe("message d'information des anciens comptes entreprise", () => {
  beforeEach(() => localStorage.clear());

  it("mémorise la fermeture par organisation", () => {
    expect(isLegacyNoticeDismissed("o1")).toBe(false);
    dismissLegacyNotice("o1");
    expect(isLegacyNoticeDismissed("o1")).toBe(true);
    expect(isLegacyNoticeDismissed("o2")).toBe(false);
    expect(localStorage.getItem(legacyNoticeKey("o1"))).toBe("1");
  });

  it("efface toutes les mémorisations à la déconnexion, sans toucher aux autres clés", () => {
    dismissLegacyNotice("o1");
    dismissLegacyNotice("o2");
    localStorage.setItem("autre", "x");
    clearLegacyNotices();
    expect(isLegacyNoticeDismissed("o1")).toBe(false);
    expect(isLegacyNoticeDismissed("o2")).toBe(false);
    expect(localStorage.getItem("autre")).toBe("x");
  });

  it("ne cible que les organisations migrées ; la clé absente vaut faux", () => {
    const list = [
      ctx({ id: "a", migrated_from_business: true }),
      ctx({ id: "b" }),
      ctx({ id: "c", migrated_from_business: undefined as unknown as boolean }),
      ctx({ id: "d", type: "PROVIDER", migrated_from_business: true }),
    ];
    expect(migratedOrganizations(list).map((c) => c.id)).toEqual(["a"]);
  });
});
