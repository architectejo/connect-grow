// Jeton d'invitation d'organisation (L1-01, ADR 0008 §5, spec E15 §4.2).
//
// Le jeton arrive dans le FRAGMENT du lien (`/organization-invitation#token=…`) : un fragment n'est jamais envoyé au serveur.
// Il est rangé en `sessionStorage` (jamais `localStorage`) pour survivre à la connexion ou à l'inscription (code OTP compris),
// puis la barre d'adresse est nettoyée. Il ne doit apparaître ni dans une URL d'API, ni dans une clé de requête, un toast,
// un journal ou une zone `aria-live` : il ne voyage que dans le CORPS d'un POST.
//
// Protection d'un onglet partagé (audit S2) : le jeton rangé expire au bout de 60 minutes ; il est lié au premier compte
// qui en obtient l'aperçu et effacé si un autre compte s'en sert ensuite ; il est effacé à la fin de session (déconnexion,
// expiration, déconnexion depuis un autre onglet : voir `AuthContext`).

export const INVITATION_PATH = "/organization-invitation";
export const INVITATION_TOKEN_KEY = "connecte.orgInvitation.v1";
/** Durée de vie du jeton rangé dans l'onglet (le lien reçu reste, lui, utilisable jusqu'à son échéance serveur). */
export const INVITATION_TOKEN_MAX_AGE_MS = 60 * 60 * 1000;
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;

interface StoredInvitation {
  token: string;
  storedAt: number;
  /** Compte qui a obtenu le premier aperçu réussi. */
  accountId?: string;
}

/**
 * Repli en mémoire si `sessionStorage` refuse l'écriture (mode privé strict, quota) : perdu au rechargement, jamais persisté.
 * Lu EN PREMIER, pour qu'un ancien jeton resté dans le stockage ne masque jamais le plus récent.
 */
let memoryRecord: StoredInvitation | null = null;

/** Aucun jeton utilisable au moment de l'appel (expiré, lié à un autre compte, effacé) : aucun appel réseau n'est fait. */
export class InvitationTokenMissingError extends Error {
  constructor() {
    super("invitation token missing");
    this.name = "InvitationTokenMissingError";
  }
}

export const isValidInvitationToken = (value: unknown): value is string => typeof value === "string" && TOKEN_PATTERN.test(value);

/** Lien de partage : le jeton va dans le fragment, jamais en query ni en chemin (contrat §2.1). */
export const buildInvitationLink = (origin: string, token: string) => `${origin}${INVITATION_PATH}#token=${token}`;

/** Jeton du fragment d'URL (`#token=…`) s'il est conforme, sinon null. */
export function tokenFromHash(hash: string): string | null {
  if (!hash || hash === "#") return null;
  const value = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return isValidInvitationToken(value) ? value : null;
}

/** Le fragment porte un paramètre `token=` (conforme ou non) : il ne doit pas rester visible. */
export const hasTokenParam = (hash: string) => /(^#|&)token=/.test(hash);

function parse(raw: string | null): StoredInvitation | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<StoredInvitation>;
    if (!isValidInvitationToken(value?.token) || typeof value.storedAt !== "number") return null;
    return { token: value.token, storedAt: value.storedAt, accountId: typeof value.accountId === "string" ? value.accountId : undefined };
  } catch {
    return null;
  }
}

function readRecord(): StoredInvitation | null {
  if (memoryRecord) return memoryRecord;
  try {
    return parse(window.sessionStorage.getItem(INVITATION_TOKEN_KEY));
  } catch {
    return null;
  }
}

function writeRecord(record: StoredInvitation): void {
  try {
    window.sessionStorage.setItem(INVITATION_TOKEN_KEY, JSON.stringify(record));
    memoryRecord = null;
  } catch {
    // Écriture refusée : l'ancien jeton ne doit pas survivre au nouveau
    memoryRecord = record;
    try {
      window.sessionStorage.removeItem(INVITATION_TOKEN_KEY);
    } catch {
      /* stockage inaccessible */
    }
  }
}

export function clearInvitationToken(): void {
  memoryRecord = null;
  try {
    window.sessionStorage.removeItem(INVITATION_TOKEN_KEY);
  } catch {
    /* rien à effacer */
  }
}

/**
 * Jeton utilisable, ou null. Effacé s'il a plus de 60 minutes, ou s'il est lié à un autre compte que `accountId`
 * (compte connu seulement : sans identifiant, aucune comparaison).
 */
export function readInvitationToken(accountId?: string | null, now: number = Date.now()): string | null {
  const record = readRecord();
  if (!record) return null;
  if (now - record.storedAt > INVITATION_TOKEN_MAX_AGE_MS || record.storedAt > now + 60_000) {
    clearInvitationToken();
    return null;
  }
  if (accountId && record.accountId && record.accountId !== accountId) {
    clearInvitationToken();
    return null;
  }
  return record.token;
}

export function storeInvitationToken(token: string, now: number = Date.now()): void {
  writeRecord({ token, storedAt: now });
}

/** Lie le jeton rangé au compte qui vient d'en obtenir l'aperçu (sans effet s'il est déjà lié). */
export function bindInvitationToken(accountId: string): void {
  const record = readRecord();
  if (!record || record.accountId) return;
  writeRecord({ ...record, accountId });
}

/**
 * Range le jeton du fragment (s'il y en a un, il remplace l'ancien) puis efface la barre d'adresse
 * (`history.replaceState`, état du routeur conservé : pas d'entrée d'historique). Le routeur est réaligné ensuite par la page
 * (`navigate(…, { replace: true })`). Sans fragment valide, relit le jeton rangé. Renvoie le jeton issu du fragment, ou null.
 * Idempotent : un second appel (mode strict de React) ne trouve plus de fragment et relit le stockage.
 */
export function ingestInvitationToken(hash: string = window.location.hash): string | null {
  const fromHash = tokenFromHash(hash);
  if (fromHash) storeInvitationToken(fromHash);
  // Un fragment qui porte `token=` est effacé même s'il est mal formé : rien de ce type ne doit rester visible
  if ((fromHash || hasTokenParam(hash)) && hasTokenParam(window.location.hash)) {
    window.history.replaceState(window.history.state, "", INVITATION_PATH);
  }
  return fromHash;
}
