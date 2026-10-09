import { describe, it, expect } from "vitest";
import { isCacheableApiContent } from "./cache-rules";

const call = (path: string, headers: Record<string, string> = {}, method = "GET") =>
  isCacheableApiContent({
    url: new URL(path, "http://localhost"),
    request: new Request("http://localhost" + path, { method, headers }),
  });

describe("isCacheableApiContent", () => {
  it("accepte une lecture publique", () => {
    expect(call("/api/marketplace/posts/")).toBe(true);
    expect(call("/api/v1/marketplace/posts/12/")).toBe(true);
    expect(call("/api/accounts/businesses/3/")).toBe(true);
  });
  it("refuse une requête authentifiée", () => {
    expect(call("/api/marketplace/posts/", { Authorization: "Bearer x" })).toBe(false);
  });
  it("refuse my_posts, quelle que soit la valeur", () => {
    expect(call("/api/marketplace/posts/?my_posts=true")).toBe(false);
    expect(call("/api/marketplace/posts/?my_posts=false")).toBe(false);
    expect(call("/api/marketplace/posts/?my_posts=")).toBe(false);
  });
  it("refuse la corbeille et mine", () => {
    expect(call("/api/marketplace/posts/trash/")).toBe(false);
    expect(call("/api/v1/marketplace/posts/mine/")).toBe(false);
  });
  it("refuse les autres routes privées et les favoris", () => {
    expect(call("/api/accounts/me/")).toBe(false);
    expect(call("/api/accounts/kyc/")).toBe(false);
    expect(call("/api/marketplace/favorites/")).toBe(false);
    expect(call("/api/interactions/conversations/")).toBe(false);
  });
  it("refuse les méthodes autres que GET", () => {
    expect(call("/api/marketplace/posts/", {}, "POST")).toBe(false);
  });
  it("refuse KYC et interactions, même sans en-tête Authorization", () => {
    expect(call("/api/accounts/kyc/documents/")).toBe(false);
    expect(call("/api/v1/interactions/messages/?conversation=x")).toBe(false);
    expect(call("/api/interactions/notifications/")).toBe(false);
  });
  it("refuse toute requête portant Authorization, y compris sur les routes publiques", () => {
    expect(call("/api/accounts/businesses/", { Authorization: "Bearer x" })).toBe(false);
  });
});
