import { describe, expect, it } from "vitest";
import fixture from "@/api/__fixtures__/contexts.json";
import type { ContextsResponse } from "@/api/types";
import { parseContexts } from "./use-contexts";

const response = fixture.response as unknown as ContextsResponse;

describe("parseContexts (contrat de contexts/)", () => {
  it("garde results et unavailable, avec leur statut", () => {
    const data = parseContexts(response);
    expect(data.results).toHaveLength(4);
    expect(data.results.every((c) => c.status === "ACTIVE")).toBe(true);
    expect(data.unavailable.map((o) => [o.status, o.role, o.capabilities])).toEqual([
      ["SUSPENDED", "OWNER", ["org.leave"]],
      ["ARCHIVED", "EDITOR", ["org.leave"]],
    ]);
  });

  it("unavailable absent ou vide : liste vide", () => {
    const { unavailable: _omit, ...withoutKey } = response;
    expect(parseContexts(withoutKey).unavailable).toEqual([]);
    expect(parseContexts({ ...response, unavailable: [] }).unavailable).toEqual([]);
  });

  it("status absent : traité comme ACTIVE ; ancien format (tableau) toléré", () => {
    const legacy = response.results.map(({ status: _status, ...rest }) => rest) as unknown as ContextsResponse["results"];
    expect(parseContexts(legacy).results.every((c) => c.status === "ACTIVE")).toBe(true);
    expect(parseContexts(legacy).unavailable).toEqual([]);
  });

  it("ignore une entrée qui ne serait ni suspendue ni archivée, ni organisation", () => {
    const odd = { ...response, unavailable: [{ ...response.results[2], status: "ACTIVE" }, { ...response.results[0], status: "SUSPENDED" }] } as unknown as ContextsResponse;
    expect(parseContexts(odd).unavailable).toEqual([]);
  });

  it("aucun champ sensible dans le contrat : ni motif, ni date, ni auteur, ni NIF, ni membres", () => {
    const keys = Object.keys(response.unavailable?.[0] ?? {}).sort();
    expect(keys).toEqual(["capabilities", "id", "migrated_from_business", "name", "org_type", "photo", "role", "status", "type"]);
  });
});
