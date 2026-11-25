/** Lien vers la connexion qui ramène ensuite l'utilisateur là où il était. */
export function loginPath(next?: string): string {
  return next && next !== "/" ? `/login?next=${encodeURIComponent(next)}` : "/login";
}

/** N'accepte qu'un chemin interne (évite les redirections ouvertes vers un autre site). */
export function safeNext(value: string | null | undefined, fallback = "/dashboard"): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return fallback;
  return value;
}
