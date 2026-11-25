import { afterEach, describe, expect, it, vi } from "vitest";

async function load(env: Record<string, string | undefined>) {
  vi.resetModules();
  vi.unstubAllEnvs();
  for (const [key, value] of Object.entries(env)) if (value !== undefined) vi.stubEnv(key, value);
  return import("./env");
}

describe("config/env", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("l'API pointe par défaut sur /api/v1/", async () => {
    const { API_URL } = await load({ VITE_API_URL: undefined });
    expect(API_URL).toBe("http://localhost:8000/api/v1/");
  });

  it("ajoute le / final manquant", async () => {
    const { API_URL } = await load({ VITE_API_URL: "https://api.example.cd/api/v1" });
    expect(API_URL).toBe("https://api.example.cd/api/v1/");
  });

  it("les médias dérivent de l'origine seule : le suffixe /api/v1/ n'y figure pas", async () => {
    const { MEDIA_BASE_URL } = await load({ VITE_API_URL: "https://api.example.cd/api/v1/", VITE_MEDIA_URL: undefined });
    expect(MEDIA_BASE_URL).toBe("https://api.example.cd");
  });

  it("VITE_MEDIA_URL prime et perd son / final", async () => {
    const { MEDIA_BASE_URL } = await load({ VITE_MEDIA_URL: "https://cdn.example.cd/" });
    expect(MEDIA_BASE_URL).toBe("https://cdn.example.cd");
  });
});
