import { describe, expect, it } from "vitest";
import { userContactLine } from "./user-contact";

describe("userContactLine", () => {
  it("préfère l'e-mail", () => expect(userContactLine({ email: "a@b.cd", phone: "+243810000000" })).toBe("a@b.cd"));
  it("se rabat sur le téléphone pour un compte sans e-mail", () => expect(userContactLine({ email: null, phone: "+243810000000" })).toBe("+243810000000"));
  it("ne renvoie jamais null ni undefined", () => {
    for (const user of [{ email: null, phone: null }, { email: null }, null, undefined]) {
      const line = userContactLine(user as never);
      expect(line).toBe("");
      expect(line).not.toMatch(/null|undefined/);
    }
  });
});
