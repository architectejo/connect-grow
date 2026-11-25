import { describe, expect, it } from "vitest";
import "@/i18n";
import { allowedChannelsOf, formatWaitDelay, revealErrorInfo, revealLink } from "./contact-reveal";

describe("allowedChannelsOf", () => {
  it("reprend allowed_channels ; sans le champ, seulement le message", () => {
    expect(allowedChannelsOf({ allowed_channels: ["MESSAGE", "CALL"] })).toEqual(["MESSAGE", "CALL"]);
    expect(allowedChannelsOf({})).toEqual(["MESSAGE"]);
    expect(allowedChannelsOf({ allowed_channels: [] })).toEqual([]);
  });
});

describe("revealLink", () => {
  it("accepte tel: et wa.me bien formés, selon le canal", () => {
    expect(revealLink("CALL", { tel_url: "tel:+243812345678", whatsapp_url: null })).toBe("tel:+243812345678");
    expect(revealLink("WHATSAPP", { tel_url: null, whatsapp_url: "https://wa.me/243812345678?text=Chaussures%20Nike" })).toContain("wa.me");
  });
  it("accepte le lien réel du serveur (titre encodé par quote(safe=''))", () => {
    const real = "https://wa.me/243891111111?text=Chaussures%20%26%20sacs%20%C3%A0%20vendre";
    expect(revealLink("WHATSAPP", { tel_url: null, whatsapp_url: real })).toBe(real);
    expect(revealLink("WHATSAPP", { tel_url: null, whatsapp_url: "https://wa.me/243891111111?text=Un_titre-simple.~" })).not.toBeNull();
  });
  it("rejette un texte prérempli contenant des caractères non encodés", () => {
    for (const text of ["a b", "<script>", "a&b=c", "x#y", "é"]) {
      expect(revealLink("WHATSAPP", { tel_url: null, whatsapp_url: `https://wa.me/243891111111?text=${text}` })).toBeNull();
    }
  });
  it("rejette un autre schéma, un autre hôte ou un lien du mauvais canal", () => {
    expect(revealLink("CALL", { tel_url: "javascript:alert(1)", whatsapp_url: null })).toBeNull();
    expect(revealLink("WHATSAPP", { tel_url: null, whatsapp_url: "https://evil.example/243812345678" })).toBeNull();
    expect(revealLink("CALL", { tel_url: null, whatsapp_url: "https://wa.me/243812345678" })).toBeNull();
  });
});

describe("formatWaitDelay", () => {
  it("arrondit par excès et accorde le pluriel", () => {
    expect(formatWaitDelay(1)).toBe("1 seconde");
    expect(formatWaitDelay(45)).toBe("45 secondes");
    expect(formatWaitDelay(61)).toBe("2 minutes");
    expect(formatWaitDelay(3600)).toBe("1 heure");
    expect(formatWaitDelay(86000)).toBe("24 heures");
    expect(formatWaitDelay(undefined)).toBe("quelques instants");
  });
});

describe("revealErrorInfo", () => {
  const err = (status: number, code?: string, headers: Record<string, string> = {}) => ({
    response: { status, data: code ? { code } : {}, headers },
  });
  it("classe chaque code du contrat", () => {
    expect(revealErrorInfo(err(403, "own_offer")).kind).toBe("blocked");
    expect(revealErrorInfo(err(403, "contact_restricted")).kind).toBe("blocked");
    expect(revealErrorInfo(err(403, "channel_not_allowed")).kind).toBe("unavailable");
    expect(revealErrorInfo(err(404, "offer_not_found")).kind).toBe("unavailable");
    expect(revealErrorInfo(err(429, "reveal_quota_ip", { "Retry-After": "10" })).kind).toBe("limit");
    expect(revealErrorInfo(err(409, "reveal_in_progress")).kind).toBe("retry");
    expect(revealErrorInfo(err(401, "not_authenticated")).kind).toBe("login");
    expect(revealErrorInfo(err(400, "channel_invalid")).kind).toBe("blocked");
    expect(revealErrorInfo(new Error("offline")).kind).toBe("retry");
  });
  it("n'affiche jamais le texte du serveur", () => {
    const info = revealErrorInfo({ response: { status: 403, data: { detail: "Forbidden", code: "own_offer" } } });
    expect(info.message).not.toMatch(/Forbidden/);
  });
});
