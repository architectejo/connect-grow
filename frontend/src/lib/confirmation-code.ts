/**
 * Code de rattachement d'une invitation Administrateur (contrat L1-01 §7.4.5 à §7.4.7, spec D2 §8.3 et §9.4).
 *
 * Secret à usage unique : ces fonctions ne font que le mettre en forme. Aucune ne le stocke, ne le journalise ni ne le
 * renvoie ailleurs que dans sa valeur de retour.
 */

/** Longueur du code : exactement 6 chiffres (contrat §7.4.6). */
export const CONFIRMATION_CODE_LENGTH = 6;

/**
 * Saisie ou collage → chiffres seulement, 6 au plus. « 482 913 », « 482-913 », « 48a2913 » donnent « 482913 ».
 * Les espaces sont RETIRÉS avant l'envoi : le serveur compte un code mal formé comme un essai faux.
 */
export function normalizeCode(input: string): string {
  return input.replace(/\D/g, "").slice(0, CONFIRMATION_CODE_LENGTH);
}

/** Le code saisi est complet (6 chiffres exactement). */
export const isCompleteCode = (value: string) => /^\d{6}$/.test(value);

/** Affichage en deux groupes de 3 : « 482 913 ». Une valeur inattendue est rendue telle quelle (aucune donnée inventée). */
export function formatCodeGroups(code: string): string {
  return /^\d{6}$/.test(code) ? `${code.slice(0, 3)} ${code.slice(3)}` : code;
}

/** Chiffres séparés par une espace, pour une lecture chiffre par chiffre par les lecteurs d'écran : « 4 8 2 9 1 3 ». */
export function spellDigits(value: string): string {
  return value.replace(/\D/g, "").split("").join(" ");
}
