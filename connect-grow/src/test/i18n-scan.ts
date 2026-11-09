import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import ts from "typescript";

/**
 * Outils d'analyse statique des sources du front, utilisés par le garde-fou d'internationalisation
 * (`src/i18n/i18n-guard.test.ts`). Rien de tout cela n'est embarqué dans l'application.
 */

export const SRC_ROOT = join(__dirname, "..");

/**
 * Fichiers et dossiers exclus de l'analyse, chacun avec sa justification.
 * Toute nouvelle exception doit être justifiée ici.
 */
export const EXCLUDED: { path: string; reason: string }[] = [
  { path: "components/ui/", reason: "composants shadcn génériques : aucun texte métier" },
  { path: "i18n/", reason: "c'est ici que vivent les textes" },
  { path: "test/", reason: "outils de test" },
  { path: "pages/DesignSystem.tsx", reason: "page de démonstration réservée au développement (import.meta.env.DEV), absente du build de production" },
];

export function sourceFiles(dir: string = SRC_ROOT): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    const rel = relative(SRC_ROOT, full).split(sep).join("/");
    if (EXCLUDED.some((e) => (e.path.endsWith("/") ? `${rel}/`.startsWith(e.path) : rel === e.path))) return [];
    if (statSync(full).isDirectory()) return name === "__fixtures__" ? [] : sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) && !/\.(test|spec)\.|\.d\.ts$/.test(name) ? [full] : [];
  });
}

export interface Finding {
  line: number;
  kind: "jsx-text" | "attribute" | "string";
  text: string;
}

const ACCENT = /[À-ÖØ-öø-ÿŒœ]/;
const LETTERS = /[A-Za-zÀ-ÿ]{2,}/;
/** Attributs dont la valeur littérale est toujours un texte visible ou lu par un lecteur d'écran. */
const VISIBLE_ATTRIBUTES = new Set([
  "placeholder", "aria-label", "aria-description", "aria-valuetext", "aria-roledescription",
  "title", "alt", "label", "description", "hint", "caption", "heading", "helperText",
]);
const BRAND_WORDMARK = "Connecte";
/** Schéma d'autorisation HTTP : valeur technique, jamais affichée. */
const AUTH_SCHEME = /^Bearer\s*$/;
/** Codes de capacité renvoyés par l'API (`org.edit_profile`) : des identifiants, pas des clés de traduction. */
const CAPABILITY_CODE = /^((org|contact|offer|review|message|stats)\.[a-z]+(_[a-z]+)+|org\.(archive|leave))$/;
const CLASS_CALLEES = new Set(["cn", "cva", "clsx", "twMerge"]);

const calleeName = (call: ts.CallExpression | ts.NewExpression): string => {
  const e = call.expression;
  if (ts.isIdentifier(e)) return e.text;
  if (ts.isPropertyAccessExpression(e)) return `${ts.isIdentifier(e.expression) ? e.expression.text : ""}.${e.name.text}`;
  return "";
};

/** Contextes où une chaîne n'est jamais un texte affiché : style, traduction déjà faite, journal, erreur de développement. */
function isIgnoredContext(node: ts.Node): boolean {
  for (let p: ts.Node | undefined = node.parent; p; p = p.parent) {
    if (ts.isImportDeclaration(p) || ts.isExportDeclaration(p) || ts.isLiteralTypeNode(p) || ts.isTypeNode(p)) return true;
    if (ts.isJsxAttribute(p) && ["className", "class", "style", "id", "htmlFor", "to", "href", "src", "d", "viewBox"].includes(p.name.getText())) return true;
    if (ts.isCallExpression(p) || ts.isNewExpression(p)) {
      const name = calleeName(p);
      // Déjà traduit, journal de développement, erreurs techniques, classes CSS, expressions régulières
      if (/^(t|i18n\.t|console\.\w+|cn|cva|clsx|twMerge|Error|RegExp|import|require)$/.test(name)) return true;
      if (/^(document\.querySelector(All)?|window\.matchMedia|localStorage\.\w+|sessionStorage\.\w+|JSON\.parse)$/.test(name)) return true;
    }
    if (ts.isThrowStatement(p)) return true;
  }
  return false;
}

/** Texte de lecture « phrase française » : accent, ou majuscule suivie de plusieurs mots. */
function looksLikeSentence(text: string): boolean {
  if (ACCENT.test(text)) return true;
  return /^[A-Z][a-z]+(\s+[a-zA-Z']+)+/.test(text.trim());
}

/**
 * Repère les textes visibles écrits en dur dans un fichier .ts/.tsx.
 *
 * Heuristique (volontairement simple, sans faux silence sur les cas courants) :
 *  1. tout texte JSX qui contient au moins deux lettres (hors espaces, ponctuation, chiffres) ;
 *  2. toute valeur littérale d'un attribut visible (placeholder, aria-label, title, alt, label, description, hint…) ;
 *  3. toute autre chaîne littérale qui contient une lettre accentuée ou qui ressemble à une phrase
 *     (majuscule initiale puis plusieurs mots), ainsi que tout modèle de chaîne (`…${x}…`) dont la partie fixe
 *     contient un mot et une espace ;
 *  hors chaînes passées à t(), classes CSS, erreurs techniques (throw / new Error), journal (console.*), imports et types.
 */
export function findHardcodedText(source: string, fileName = "file.tsx"): Finding[] {
  const sf = ts.createSourceFile(fileName, source, ts.ScriptTarget.ES2020, true, fileName.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out: Finding[] = [];
  const lineOf = (n: ts.Node) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;

  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      const text = node.text.replace(/\s+/g, " ").trim();
      // « Connecte » seul : moitié du logotype « Connecte+ » (nom de marque suivi de <span>+</span>), non traduisible
      if (text && text !== BRAND_WORDMARK && LETTERS.test(text)) out.push({ line: lineOf(node), kind: "jsx-text", text });
    } else if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const text = node.text;
      const attr = ts.isJsxAttribute(node.parent) ? node.parent.name.getText() : undefined;
      if (attr && VISIBLE_ATTRIBUTES.has(attr) && LETTERS.test(text)) out.push({ line: lineOf(node), kind: "attribute", text });
      else if (!AUTH_SCHEME.test(text) && !isIgnoredContext(node) && looksLikeSentence(text)) out.push({ line: lineOf(node), kind: "string", text });
    } else if (ts.isTemplateExpression(node)) {
      const fixed = [node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join("");
      const pathLike = /[/?&=#]/.test(fixed);
      if (!AUTH_SCHEME.test(fixed) && !isIgnoredContext(node) && !pathLike && ((/\s/.test(fixed) && /[A-Za-zÀ-ÿ]{3,}/.test(fixed)) || ACCENT.test(fixed))) {
        out.push({ line: lineOf(node), kind: "string", text: fixed });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

/** Argument de `liste.includes("org.archive")` : un test d'appartenance (capacités de l'API), jamais une clé de traduction. */
const isIncludesArgument = (node: ts.Node) =>
  ts.isCallExpression(node.parent) && ts.isPropertyAccessExpression(node.parent.expression) && node.parent.expression.name.text === "includes";

/** Clés de traduction utilisées dans un fichier : t("…"), i18n.t("…"), et chaînes qui ressemblent à une clé existante. */
export interface KeyUse {
  line: number;
  key: string;
  /** Vrai quand la clé est un modèle (`a.b.${x}`) : seul le préfixe fixe est vérifié. */
  dynamic: boolean;
}

export function findKeyUses(source: string, topLevelKeys: Set<string>, fileName = "file.tsx"): KeyUse[] {
  const sf = ts.createSourceFile(fileName, source, ts.ScriptTarget.ES2020, true, fileName.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out: KeyUse[] = [];
  const lineOf = (n: ts.Node) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
  const seen = new Set<ts.Node>();

  const record = (arg: ts.Expression | undefined) => {
    if (!arg) return;
    if (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) {
      seen.add(arg);
      out.push({ line: lineOf(arg), key: arg.text, dynamic: false });
    } else if (ts.isTemplateExpression(arg)) {
      seen.add(arg);
      out.push({ line: lineOf(arg), key: arg.head.text, dynamic: true });
    } else if (ts.isConditionalExpression(arg)) {
      record(arg.whenTrue);
      record(arg.whenFalse);
    }
  };

  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && /^(t|i18n\.t)$/.test(calleeName(node))) record(node.arguments[0]);
    // Clés rangées dans des données (labelKey: "nav.home") : chaîne qui commence par un domaine connu de fr.ts
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && !seen.has(node)) {
      const m = /^([a-z][A-Za-z0-9]*)\.[A-Za-z0-9_.]+$/.exec(node.text);
      const inKeyProperty = ts.isPropertyAssignment(node.parent) && /Key$/.test(node.parent.name.getText());
      if (m && !CAPABILITY_CODE.test(node.text) && !isIncludesArgument(node) && (inKeyProperty || topLevelKeys.has(m[1])) && !ts.isImportDeclaration(node.parent) && !isIgnoredContext(node)) {
        out.push({ line: lineOf(node), key: node.text, dynamic: false });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

export const readSource = (file: string) => readFileSync(file, "utf8");
