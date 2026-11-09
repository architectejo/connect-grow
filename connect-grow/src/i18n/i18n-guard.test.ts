import { describe, expect, it } from "vitest";
import { relative, sep } from "node:path";
import fr from "./locales/fr";
import { EXCLUDED, SRC_ROOT, findHardcodedText, findKeyUses, readSource, sourceFiles } from "@/test/i18n-scan";

/**
 * Garde-fou L0-18 : tous les textes visibles passent par l'i18n (`src/i18n/locales/fr.ts`).
 *
 * Deux contrôles statiques sur `src/**` (hors tests et exceptions justifiées dans `@/test/i18n-scan`) :
 *  1. aucun texte français écrit en dur : texte JSX, attributs visibles (placeholder, aria-label, title, alt, label…),
 *     toasts, messages de validation, chaînes accentuées ou en forme de phrase ;
 *  2. toute clé utilisée par `t("…")` (ou rangée dans une donnée, ex. `labelKey: "nav.home"`) existe dans `fr.ts`.
 *
 * L'heuristique complète est documentée dans `findHardcodedText` (src/test/i18n-scan.ts).
 */

type Tree = { [key: string]: string | Tree };
const tree = fr as unknown as Tree;
const files = sourceFiles();
const rel = (file: string) => relative(SRC_ROOT, file).split(sep).join("/");

/** Chemin pointé → valeur (feuille, ou sous-arbre). */
function lookup(path: string): string | Tree | undefined {
  let node: string | Tree | undefined = tree;
  for (const part of path.split(".")) {
    if (node === undefined || typeof node === "string") return undefined;
    node = node[part];
  }
  return node;
}

/** Une clé existe si elle est une feuille, ou si une de ses formes plurielles (`_one`, `_other`…) existe. */
const keyExists = (key: string) => {
  const found = lookup(key);
  if (typeof found === "string") return true;
  return ["_zero", "_one", "_two", "_few", "_many", "_other"].some((suffix) => typeof lookup(key + suffix) === "string");
};

describe("garde-fou i18n : aucun texte en dur", () => {
  it("analyse bien les sources de l'application", () => {
    expect(files.length).toBeGreaterThan(100);
    expect(files.some((f) => rel(f) === "pages/Marketplace.tsx")).toBe(true);
    // Les exceptions sont explicites et justifiées
    for (const exception of EXCLUDED) expect(exception.reason.length).toBeGreaterThan(10);
  });

  it("aucun fichier de src ne contient de texte français littéral", () => {
    const offenders = files.flatMap((file) =>
      findHardcodedText(readSource(file), file).map((f) => `${rel(file)}:${f.line} [${f.kind}] ${f.text}`),
    );
    expect(offenders).toEqual([]);
  });

  it("détecte un texte JSX, un attribut et une chaîne en dur (le garde-fou fonctionne)", () => {
    const sample = `
      export const A = () => <p placeholder="Rechercher">Bonjour à tous</p>;
      export const message = "Une erreur est survenue";
      export const withVar = \`\${n} annonces restantes\`;
    `;
    const kinds = findHardcodedText(sample).map((f) => f.kind);
    expect(kinds).toEqual(expect.arrayContaining(["jsx-text", "attribute", "string"]));
    expect(findHardcodedText(sample)).toHaveLength(4);
  });

  it("ignore les chaînes techniques et déjà traduites", () => {
    const sample = `
      import { x } from "@/lib/é";
      export const A = () => <p className="flex items-center gap-2">{t("home.title")}</p>;
      export const e = () => { throw new Error("Doit être utilisé dans un fournisseur"); };
      console.error("Erreur de développement");
      export const url = \`/organizations/\${id}/verification\`;
    `;
    expect(findHardcodedText(sample)).toEqual([]);
  });
});

describe("garde-fou i18n : les clés utilisées existent dans fr.ts", () => {
  const topLevel = new Set(Object.keys(tree));

  it("toutes les clés t(\"…\") et toutes les clés rangées dans des données existent", () => {
    const missing = files.flatMap((file) =>
      findKeyUses(readSource(file), topLevel, file)
        .filter(({ key }) => key !== "")
        .filter(({ key, dynamic }) => {
          if (!dynamic) return !keyExists(key);
          // Clé construite (`badge.${x}`) : le préfixe fixe doit au moins désigner un groupe existant
          const prefix = key.replace(/\.$/, "");
          return prefix !== "" && typeof lookup(prefix) !== "object";
        })
        .map(({ line, key }) => `${rel(file)}:${line} ${key}`),
    );
    expect(missing).toEqual([]);
  });

  it("repère une clé manquante (le garde-fou fonctionne)", () => {
    const uses = findKeyUses(`t("nav.home"); t("nav.inexistante"); const x = { labelKey: "nav.fantome" };`, topLevel);
    const missing = uses.filter(({ key }) => !keyExists(key)).map(({ key }) => key);
    expect(missing).toEqual(["nav.inexistante", "nav.fantome"]);
  });

  it("comprend les pluriels (_one / _other)", () => {
    expect(keyExists("rating.count")).toBe(true);
    expect(keyExists("rating.inexistante")).toBe(false);
  });
});
