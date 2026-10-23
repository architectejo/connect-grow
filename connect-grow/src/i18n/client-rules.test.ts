import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import fr from "./locales/fr";

/**
 * Règles client verrouillées (CLAUDE.md §4) vérifiées sur les textes et le code du front :
 * règle 3 (jamais « Vérifié » seul, jamais « garanti »/« certifié »), règle 4 (aucun score de confiance),
 * règle 2 (aucun plan lié à une vérification ou un rôle), règle 5 (« Sponsorisé »).
 */
type Tree = { [key: string]: string | Tree };

function leaves(tree: Tree, path = ""): { path: string; text: string }[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string" ? [{ path: `${path}${key}`, text: value }] : leaves(value, `${path}${key}.`),
  );
}
const strings = leaves(fr as unknown as Tree);

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === "ui" || name === "__fixtures__" ? [] : sources(full);
    return /\.(ts|tsx)$/.test(name) && !/\.test\./.test(name) ? [full] : [];
  });
}

describe("textes de l'interface", () => {
  it("aucun texte ne se réduit à « Vérifié » : une mention dit ce qui a été vérifié", () => {
    expect(strings.filter(({ text }) => /^vérifié(e|s)?$/i.test(text.trim())).map(({ path }) => path)).toEqual([]);
    expect(strings.find(({ path }) => path === "badge.verified")).toBeUndefined();
  });

  it("jamais « garanti », « certifié » ni « de confiance » pour une vérification, hors négation explicite", () => {
    const risky = strings.filter(({ path, text }) => /^(claims|verif|org|orgNew|orgEdit|team|seller|directory|legacy|dashboard|profiles|provider|kyc)\./.test(path) && /garanti|certifi|de confiance|recommand/i.test(text));
    for (const { path, text } of risky) {
      // Seules les négations sont admises : « ni une garantie », « ne garantit ni… », « ni une recommandation »
      expect(text, path).toMatch(/ne garantit|ni une garantie|ni une recommandation|n'est ni/);
    }
  });

  it("aucun « score de confiance » (règle 4)", () => {
    expect(strings.filter(({ text }) => /score de confiance|trust score|note globale/i.test(text)).map(({ path }) => path)).toEqual([]);
  });

  it("la vérification ne s'achète pas et ne dépend ni d'un plan ni d'un rôle (règle 2 et 3)", () => {
    const verif = strings
      .filter(({ path }) => /^(verif|claims|org|dashboard)\./.test(path) && path !== "verif.notPaid")
      .map(({ text }) => text)
      .join(" ");
    expect(verif).not.toMatch(/abonnement|forfait|premium|payant|tarif/i);
    expect(strings.find(({ path }) => path === "verif.notPaid")?.text).toMatch(/ne peut pas être achetée/);
  });

  it("le badge « Sponsorisé » garde son libellé", () => {
    expect(strings.find(({ path }) => path === "badge.sponsored")?.text).toBe("Sponsorisé");
  });

  it("le mot « contexte » n'apparaît jamais à l'écran (D1)", () => {
    const hits = strings.filter(({ path, text }) => /\bcontextes?\b/i.test(text) && !/^errors\.deny\./.test(path));
    expect(hits.map(({ path }) => path)).toEqual([]);
  });
});

describe("code source", () => {
  const files = sources(resolve(process.cwd(), "src"));

  it("plus aucun badge « Vérifié » seul (StatusBadge kind=verified)", () => {
    const offenders = files.filter((file) => /kind=\{?["']verified["']/.test(readFileSync(file, "utf-8")) || /badge\.verified/.test(readFileSync(file, "utf-8")));
    expect(offenders).toEqual([]);
  });

  it("plus d'usage de l'ancien profil entreprise ni du type de compte", () => {
    const pattern = /business_profile|user_type|accounts\/businesses/;
    const offenders = files.filter((file) => pattern.test(readFileSync(file, "utf-8")));
    expect(offenders.map((file) => file.replace(process.cwd(), ""))).toEqual([]);
  });
});
