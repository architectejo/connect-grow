import { describe, expect, it } from "vitest";
import { CONFIRMATION_CODE_LENGTH, formatCodeGroups, isCompleteCode, normalizeCode, spellDigits } from "./confirmation-code";

describe("code de rattachement (L1-01-F2bis)", () => {
  it("normalizeCode : espaces, tirets et lettres retirés, 6 chiffres au plus", () => {
    expect(normalizeCode("482 913")).toBe("482913");
    expect(normalizeCode(" 482-913 ")).toBe("482913");
    expect(normalizeCode("48a2b913")).toBe("482913");
    expect(normalizeCode("4829131234")).toBe("482913");
    expect(normalizeCode("")).toBe("");
    expect(normalizeCode("abc")).toBe("");
    expect(normalizeCode("٤٨٢")).toBe("");
    expect(CONFIRMATION_CODE_LENGTH).toBe(6);
  });

  it("isCompleteCode : exactement 6 chiffres", () => {
    expect(isCompleteCode("482913")).toBe(true);
    expect(isCompleteCode("48291")).toBe(false);
    expect(isCompleteCode("482 913")).toBe(false);
    expect(isCompleteCode("4829134")).toBe(false);
  });

  it("formatCodeGroups : deux groupes de 3 ; valeur inattendue rendue telle quelle", () => {
    expect(formatCodeGroups("482913")).toBe("482 913");
    expect(formatCodeGroups("12345")).toBe("12345");
  });

  it("spellDigits : chiffres séparés pour une lecture chiffre par chiffre ; puces ignorées", () => {
    expect(spellDigits("482913")).toBe("4 8 2 9 1 3");
    expect(spellDigits("••47")).toBe("4 7");
  });
});
