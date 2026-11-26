import { describe, expect, it } from "vitest";
import fr from "@/i18n/locales/fr";
import { ACCESS_GROUPS, CAPABILITY_GROUPS, capabilityLabelKey, groupCapabilities } from "./role-access";

type Tree = { [key: string]: string | Tree };
const lookup = (path: string) => path.split(".").reduce<string | Tree | undefined>((node, part) => (typeof node === "object" ? node[part] : undefined), fr as unknown as Tree);

describe("groupCapabilities (spec D2 §9.2)", () => {
  it("chaque code de la matrice a un libellé, chaque thème a un titre", () => {
    for (const code of Object.keys(CAPABILITY_GROUPS)) expect(typeof lookup(capabilityLabelKey(code)), code).toBe("string");
    for (const group of ACCESS_GROUPS) expect(typeof lookup(`access.group.${group}`), group).toBe("string");
  });

  it("regroupe par thème dans l'ordre de la table, quel que soit l'ordre reçu", () => {
    const result = groupCapabilities(["stats.view", "org.leave", "offer.publish", "org.view_internal", "offer.view_internal"]);
    expect(result.groups).toEqual([
      { group: "organization", codes: ["org.view_internal", "org.leave"] },
      { group: "offers", codes: ["offer.view_internal", "offer.publish"] },
      { group: "stats", codes: ["stats.view"] },
    ]);
    expect(result.others).toBe(0);
  });

  it("rôle Membre : deux accès dans « Organisation »", () => {
    expect(groupCapabilities(["org.leave", "org.view_internal"]).groups).toEqual([{ group: "organization", codes: ["org.view_internal", "org.leave"] }]);
  });

  it("un code inconnu n'est jamais masqué : il est compté ; doublons retirés", () => {
    const result = groupCapabilities(["org.leave", "events.create", "events.create", "org.leave", "x.y"]);
    expect(result.groups).toEqual([{ group: "organization", codes: ["org.leave"] }]);
    expect(result.others).toBe(2);
  });

  it("libellés de facturation : un accès, jamais un plan ni un abonnement (règle 2)", () => {
    expect(String(lookup("access.cap.billing_purchase"))).not.toMatch(/plan|abonnement/i);
  });
});
