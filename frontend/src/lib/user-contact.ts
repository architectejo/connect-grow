import type { User } from "@/api/types";

/** Ligne d'identification affichée sous le nom : e-mail, sinon téléphone, sinon chaîne vide (jamais « null »). */
export function userContactLine(user: Pick<User, "email" | "phone"> | null | undefined): string {
  return user?.email || user?.phone || "";
}
