import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { ContactActions } from "./ContactActions";

describe("ContactActions", () => {
  it.each(["stack", "bar"] as const)("ne rend aucun lien tel: ni wa.me (%s)", (layout) => {
    const { container } = render(<ContactActions layout={layout} onMessage={() => {}} />);
    expect(container.querySelectorAll("a")).toHaveLength(0);
    expect(container.innerHTML).not.toMatch(/tel:|wa\.me/);
  });

  it("garde l'envoi de message et annonce le contact téléphonique à venir (layout stack)", () => {
    const onMessage = vi.fn();
    render(<ContactActions onMessage={onMessage} />);
    fireEvent.click(screen.getByRole("button", { name: "Envoyer un message" }));
    expect(onMessage).toHaveBeenCalledOnce();
    expect(screen.getByText(/Bientôt disponible : le contact par téléphone/)).toBeInTheDocument();
  });
});
