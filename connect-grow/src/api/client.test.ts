import axios, { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_EXPIRED_EVENT, tokenStorage } from "@/lib/tokens";
import apiClient from "./client";

const reply = (config: InternalAxiosRequestConfig, status: number, data: unknown = {}, headers = {}): Promise<AxiosResponse> => {
  const response = { data, status, statusText: "", headers, config } as AxiosResponse;
  return status >= 200 && status < 300
    ? Promise.resolve(response)
    : Promise.reject(new AxiosError(`HTTP ${status}`, String(status), config, null, response));
};

describe("intercepteur de rafraîchissement du jeton", () => {
  let seen: { url?: string; auth?: string }[];
  let respond: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;
  const original = apiClient.defaults.adapter;

  beforeEach(() => {
    localStorage.clear();
    seen = [];
    apiClient.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      seen.push({ url: config.url, auth: config.headers.Authorization as string | undefined });
      return respond(config);
    }) as AxiosAdapter;
    tokenStorage.set("vieux-acces", "refresh-1");
  });

  afterEach(() => {
    apiClient.defaults.adapter = original;
    vi.restoreAllMocks();
  });

  it("rafraîchit puis rejoue la requête après un 401", async () => {
    vi.spyOn(axios, "post").mockResolvedValue({ data: { access: "nouvel-acces", refresh: "refresh-2" } });
    respond = (config) => (config.headers.Authorization === "Bearer nouvel-acces" ? reply(config, 200, { ok: true }) : reply(config, 401));

    const { data } = await apiClient.get("accounts/me/");

    expect(data).toEqual({ ok: true });
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(tokenStorage.getRefresh()).toBe("refresh-2");
  });

  it("ne boucle pas et garde la session quand le refresh répond 429", async () => {
    const post = vi.spyOn(axios, "post").mockRejectedValue(
      new AxiosError("429", "429", undefined, null, { status: 429, data: {}, headers: { "retry-after": "20" } } as unknown as AxiosResponse),
    );
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    respond = (config) => reply(config, 401);

    await expect(apiClient.get("accounts/me/")).rejects.toMatchObject({ response: { status: 429 } });

    expect(post).toHaveBeenCalledTimes(1); // un seul essai de refresh
    expect(seen).toHaveLength(1); // la requête d'origine n'est pas rejouée
    expect(tokenStorage.getRefresh()).toBe("refresh-1"); // session conservée
    expect(expired).not.toHaveBeenCalled();
    window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
  });

  it("ferme la session quand le refresh est refusé (401)", async () => {
    vi.spyOn(axios, "post").mockRejectedValue(
      new AxiosError("401", "401", undefined, null, { status: 401, data: {}, headers: {} } as unknown as AxiosResponse),
    );
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    respond = (config) => (config.headers.Authorization ? reply(config, 401) : reply(config, 200, []));

    await apiClient.get("marketplace/posts/");

    expect(expired).toHaveBeenCalledTimes(1);
    expect(tokenStorage.getAccess()).toBeNull();
    window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
  });

  it("ne tente aucun rafraîchissement sur la déconnexion", async () => {
    const post = vi.spyOn(axios, "post");
    respond = (config) => reply(config, 401);

    await expect(apiClient.post("accounts/logout/", { refresh: "refresh-1" })).rejects.toMatchObject({ response: { status: 401 } });

    expect(post).not.toHaveBeenCalled();
  });

  it("ne relance pas un 429 ordinaire", async () => {
    const post = vi.spyOn(axios, "post");
    respond = (config) => reply(config, 429, {}, { "retry-after": "5" });

    await expect(apiClient.post("interactions/contacts/", {})).rejects.toMatchObject({ response: { status: 429 } });

    expect(seen).toHaveLength(1);
    expect(post).not.toHaveBeenCalled();
  });
});
