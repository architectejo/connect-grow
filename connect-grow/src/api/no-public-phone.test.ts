import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });

describe("règle 10 : pas de téléphone public", () => {
  const files = walk("src").filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f));

  it("aucune source ne construit de lien tel: ni wa.me", () => {
    const offenders = files.filter((f) => /["'`]tel:|wa\.me/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });

  it("aucune source ne lit seller.phone", () => {
    const offenders = files.filter((f) => /seller\??\.phone/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });

  it("le type Seller n'expose ni phone ni email", () => {
    const src = readFileSync("src/api/types.ts", "utf8");
    const block = src.slice(src.indexOf("export interface Seller"), src.indexOf("export interface PostImage"));
    expect(block).not.toMatch(/\b(phone|email)\??:/);
  });
});
