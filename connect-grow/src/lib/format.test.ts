import { describe, expect, it } from "vitest";
import { formatClockTime, formatDayMonth, formatMonthYear } from "./format";

describe("dates à l'heure de Kinshasa", () => {
  it("affiche l'heure locale d'un instant avec décalage (+01:00)", () => {
    expect(formatClockTime("2026-10-09T14:05:00.123456+01:00")).toBe("14:05");
  });

  it("convertit un instant UTC en heure de Kinshasa", () => {
    expect(formatClockTime("2026-10-09T13:05:00Z")).toBe("14:05");
  });

  it("change de jour à minuit de Kinshasa, pas à minuit UTC", () => {
    expect(formatDayMonth(new Date("2026-10-09T23:30:00Z"))).toBe("10/10");
    expect(formatDayMonth(new Date("2026-10-09T22:30:00Z"))).toBe("09/10");
  });

  it("donne le mois et l'année en français", () => {
    expect(formatMonthYear("2026-10-31T23:30:00Z")).toBe("novembre 2026");
  });

  it("renvoie une chaîne vide pour une date invalide", () => {
    expect(formatClockTime("pas une date")).toBe("");
    expect(formatMonthYear("pas une date")).toBe("");
  });
});
