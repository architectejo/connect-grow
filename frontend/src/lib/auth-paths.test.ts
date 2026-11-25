import { describe, it, expect } from "vitest";
import { loginPath, safeNext } from "./auth-paths";

describe("safeNext", () => {
  it("accepte un chemin interne", () => {
    expect(safeNext("/marketplace?x=1")).toBe("/marketplace?x=1");
  });
  it("refuse les redirections vers un autre site", () => {
    expect(safeNext("//evil.com")).toBe("/dashboard");
    expect(safeNext("/\\evil.com")).toBe("/dashboard");
    expect(safeNext("https://evil.com")).toBe("/dashboard");
  });
  it("utilise la valeur de repli si vide", () => {
    expect(safeNext(null)).toBe("/dashboard");
    expect(safeNext("", "/")).toBe("/");
  });
});

describe("loginPath", () => {
  it("encode la destination", () => {
    expect(loginPath("/a?b=1")).toBe("/login?next=%2Fa%3Fb%3D1");
  });
  it("ignore la racine", () => {
    expect(loginPath("/")).toBe("/login");
    expect(loginPath()).toBe("/login");
  });
});
