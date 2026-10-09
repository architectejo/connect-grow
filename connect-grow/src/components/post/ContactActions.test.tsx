import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import type { Post } from "@/api/types";
import { ContactActions } from "./ContactActions";

// Vendeur sans téléphone, comme dans les réponses publiques (règle 10).
const post = { id: "p1", title: "Vélo", seller: { id: "s1", full_name: "Awa", user_type: "PARTICULIER" } } as unknown as Post;
// Même si un ancien backend renvoyait encore un numéro, le front ne doit pas le rendre.
const legacyPost = { ...post, seller: { ...post.seller, phone: "+243812345678" } } as unknown as Post;

describe("ContactActions", () => {
  it.each(["stack", "bar"] as const)("ne rend aucun lien tel: ni wa.me (%s)", (layout) => {
    for (const p of [post, legacyPost]) {
      const { container, unmount } = render(<ContactActions post={p} layout={layout} onMessage={() => {}} />);
      expect(container.querySelectorAll("a")).toHaveLength(0);
      expect(container.innerHTML).not.toMatch(/tel:|wa\.me|243812345678/);
      unmount();
    }
  });

  it("garde l'envoi de message et annonce le contact téléphonique à venir", () => {
    const onMessage = vi.fn();
    render(<ContactActions post={post} onMessage={onMessage} />);
    fireEvent.click(screen.getByRole("button", { name: "Envoyer un message" }));
    expect(onMessage).toHaveBeenCalledOnce();
    expect(screen.getByText(/Bientôt disponible : le contact par téléphone/)).toBeInTheDocument();
  });
});
