import { describe, expect, it } from "vitest";

// Sources lues à la compilation : indépendant du répertoire de travail.
const modules = import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const sources = Object.entries(modules).filter(([path]) => !/\.test\.tsx?$/.test(path));

describe("règle 10 : pas de téléphone public", () => {
  it("charge bien les sources", () => {
    expect(sources.length).toBeGreaterThan(50);
  });

  it("aucune source ne construit de lien tel: ni wa.me", () => {
    expect(sources.filter(([, src]) => /["'`]tel:|wa\.me/.test(src)).map(([p]) => p)).toEqual([]);
  });

  it("aucune source ne lit seller.phone", () => {
    expect(sources.filter(([, src]) => /seller\??\.phone/.test(src)).map(([p]) => p)).toEqual([]);
  });

  it("le type Seller n'expose ni phone ni email", () => {
    const types = modules["/src/api/types.ts"];
    const block = /export interface Seller\s*\{[\s\S]*?\n\}/.exec(types)?.[0];
    expect(block).toBeDefined();
    expect(block).not.toMatch(/\b(phone|email)\??:/);
  });
});
