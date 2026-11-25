import { describe, expect, it } from "vitest";
import "@/i18n";
import type { AppNotification } from "@/api/types";
import { contextFilterOptions, filterNotifications, notificationContextLabel } from "./notifications";

const ORG = { type: "ORGANIZATION" as const, id: "11111111-1111-4111-8111-111111111111", name: "Atelier X" };
const PROVIDER = { type: "PROVIDER" as const, id: "22222222-2222-4222-8222-222222222222", name: "Marie couture" };

const make = (id: string, over: Partial<AppNotification> = {}): AppNotification => ({
  id,
  notification_type: "MESSAGE",
  title: "t",
  content: "c",
  is_read: false,
  created_at: "2026-10-24T10:00:00+01:00",
  context: null,
  ...over,
});

const list = [
  make("a", { context: ORG }),
  make("b", { context: null, is_read: true }),
  make("c", { context: PROVIDER }),
  make("d", { context: ORG, is_read: true }),
];

describe("notificationContextLabel", () => {
  it("nomme l'organisation ou le prestataire", () => {
    expect(notificationContextLabel(ORG)).toBe("Organisation Atelier X");
    expect(notificationContextLabel(PROVIDER)).toBe("Prestataire Marie couture");
  });

  it("sans nom (profil supprimé), n'affiche que le type", () => {
    expect(notificationContextLabel({ ...ORG, name: "" })).toBe("Organisation");
    expect(notificationContextLabel({ ...PROVIDER, name: null as unknown as string })).toBe("Prestataire");
  });
});

describe("contextFilterOptions", () => {
  it("aucune option tant qu'il n'y a que des notifications personnelles", () => {
    expect(contextFilterOptions([make("x"), make("y", { is_read: true })])).toEqual([]);
    expect(contextFilterOptions([])).toEqual([]);
  });

  it("une option par profil (sans doublon), « personnelles » seulement s'il y en a", () => {
    const options = contextFilterOptions(list);
    expect(options.map((o) => o.value)).toEqual(["all", "personal", `ORGANIZATION:${ORG.id}`, `PROVIDER:${PROVIDER.id}`]);
    expect(options.map((o) => o.label)).toEqual(["Tous les profils", "Personnelles", "Organisation Atelier X", "Prestataire Marie couture"]);
    expect(contextFilterOptions([make("a", { context: ORG })]).map((o) => o.value)).toEqual(["all", `ORGANIZATION:${ORG.id}`]);
  });
});

describe("filterNotifications", () => {
  const ids = (items: AppNotification[]) => items.map((n) => n.id);

  it("sans filtre : tout", () => {
    expect(ids(filterNotifications(list))).toEqual(["a", "b", "c", "d"]);
  });

  it("personnelles : context nul seulement", () => {
    expect(ids(filterNotifications(list, { context: "personal" }))).toEqual(["b"]);
  });

  it("un profil précis", () => {
    expect(ids(filterNotifications(list, { context: `ORGANIZATION:${ORG.id}` }))).toEqual(["a", "d"]);
    expect(ids(filterNotifications(list, { context: `PROVIDER:${PROVIDER.id}` }))).toEqual(["c"]);
  });

  it("se combine avec « non lues »", () => {
    expect(ids(filterNotifications(list, { unreadOnly: true, context: `ORGANIZATION:${ORG.id}` }))).toEqual(["a"]);
    expect(ids(filterNotifications(list, { unreadOnly: true }))).toEqual(["a", "c"]);
  });
});
