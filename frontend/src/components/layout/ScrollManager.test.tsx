import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScrollManager } from "./ScrollManager";

const renderAt = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <ScrollManager />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.useFakeTimers();
  window.scrollTo = vi.fn() as never;
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("ScrollManager", () => {
  it("descend jusqu'à une ancre simple", () => {
    const target = document.createElement("div");
    target.id = "avis";
    target.scrollIntoView = vi.fn();
    document.body.appendChild(target);
    renderAt("/post/1#avis");
    vi.advanceTimersByTime(60);
    expect(target.scrollIntoView).toHaveBeenCalled();
    target.remove();
  });

  it("un fragment porteur de paramètres (#token=…) n'est pas lu comme une ancre", () => {
    const lookup = vi.spyOn(document, "getElementById");
    renderAt("/organization-invitation#token=abc_DEF-123");
    vi.advanceTimersByTime(60);
    expect(lookup).not.toHaveBeenCalled();
  });

  it("un fragment mal encodé ne fait pas planter la page", () => {
    const lookup = vi.spyOn(document, "getElementById");
    renderAt("/page#section%E0%A4%A");
    expect(() => vi.advanceTimersByTime(60)).not.toThrow();
    expect(lookup).not.toHaveBeenCalled();
  });
});
