// Jeton d'invitation d'organisation (L1-01, ADR 0008 §5, spec E15 §4.2).
//
// Le jeton arrive dans le FRAGMENT du lien (`/organization-invitation#token=…`) : un fragment n'est jamais envoyé au serveur.
// Il est rangé en `sessionStorage` (jamais `localStorage`) pour survivre à la connexion ou à l'inscription (code OTP compris),
// puis la barre d'adresse est nettoyée. Il ne doit apparaître ni dans une URL d'API, ni dans une clé de requête, un toast,
// un journal ou une zone `aria-live` : il ne voyage que dans le CORPS d'un POST.

export const INVITATION_PATH = "/organization-invitation";
export const INVITATION_TOKEN_KEY = "connecte.orgInvitation.v1";
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;

/** Repli en mémoire si `sessionStorage` est inaccessible (mode privé strict) : perdu au rechargement, jamais persisté. */
let memoryToken: string | null = null;

export const isValidInvitationToken = (value: unknown): value is string => typeof value === "string" && TOKEN_PATTERN.test(value);

/** Lien de partage : le jeton va dans le fragment, jamais en query ni en chemin (contrat §2.1). */
export const buildInvitationLink = (origin: string, token: string) => `${origin}${INVITATION_PATH}#token=${token}`;

/** Jeton du fragment d'URL (`#token=…`) s'il est conforme, sinon null. */
export function tokenFromHash(hash: string): string | null {
  if (!hash || hash === "#") return null;
  const value = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return isValidInvitationToken(value) ? value : null;
}

const hasTokenParam = (hash: string) => /(^#|&)token=/.test(hash);

export function readInvitationToken(): string | null {
  try {
    const stored = window.sessionStorage.getItem(INVITATION_TOKEN_KEY);
    if (isValidInvitationToken(stored)) return stored;
  } catch {
    /* stockage inaccessible : repli mémoire */
  }
  return memoryToken;
}

export function storeInvitationToken(token: string): void {
  memoryToken = null;
  try {
    window.sessionStorage.setItem(INVITATION_TOKEN_KEY, token);
  } catch {
    memoryToken = token;
  }
}

export function clearInvitationToken(): void {
  memoryToken = null;
  try {
    window.sessionStorage.removeItem(INVITATION_TOKEN_KEY);
  } catch {
    /* rien à effacer */
  }
}

/**
 * À appeler au montage de la page, avant tout appel réseau. Range le jeton du fragment puis efface la barre d'adresse
 * (`history.replaceState`, état du routeur conservé : pas d'entrée d'historique, le jeton n'y reste pas). Sans fragment valide, relit `sessionStorage`.
 * Idempotent : un second appel (mode strict de React) retrouve le jeton rangé.
 */
export function ingestInvitationToken(): string | null {
  const hash = window.location.hash;
  const fromHash = tokenFromHash(hash);
  if (fromHash) storeInvitationToken(fromHash);
  // Un fragment qui porte `token=` est effacé même s'il est mal formé : rien de ce type ne doit rester visible
  if (fromHash || hasTokenParam(hash)) window.history.replaceState(window.history.state, "", INVITATION_PATH);
  return fromHash ?? readInvitationToken();
}
