"""Règles pures de la conversion des comptes entreprise en organisations (L0-09 T9-1, ADR 0006 §20).

Aucun modèle ni accès base : ce module est partagé par la migration `identity 0011` et par la commande de
pré-vol `check_legacy_conversion`, pour que les deux appliquent exactement le même nettoyage. Il disparaît avec
les migrations de conversion à la réinitialisation de fin de projet (spec T9, section 3.3).
"""
import unicodedata

ORG_TYPE = 'ENTREPRISE'  # le profil n'avait pas de type ; correction par le personnel (spec T9, Q6)
NAME_MAX_LENGTH = 255
NAME_MIN_LENGTH = 2
DESCRIPTION_MAX_LENGTH = 2000
MAX_CATEGORIES = 5
SUSPENSION_REASON = 'other'
# Sanctions de `moderation` qui bloquent le compte (copie volontaire des constantes de `Sanction`, lues sans import
# de modèle : une migration ne dépend pas du code courant d'un autre domaine).
BLOCKING_SANCTION_TYPES = ('SUSPENSION_TEMPORAIRE', 'BANNISSEMENT')
_STRIPPED_CATEGORIES = {'Cc', 'Cf', 'Zl', 'Zp'}
_SCRIPTS = ('LATIN', 'CYRILLIC', 'GREEK')


def clean_name_full(raw):
    """Nettoyage non tronqué : caractères Cc/Cf/Zl/Zp retirés, espaces repliés, bords retirés. Pas de NFKC (une
    marque ne doit pas être modifiée)."""
    text = ''.join(' ' if ch in '\t\n\r' else ch for ch in (raw or ''))
    text = ''.join(ch for ch in text if unicodedata.category(ch) not in _STRIPPED_CATEGORIES)
    return ' '.join(text.split())


def clean_name(raw):
    """Nom converti : nettoyage puis 255 caractères au plus. Peut renvoyer une chaîne vide ou trop courte."""
    return clean_name_full(raw)[:NAME_MAX_LENGTH].strip()


def needs_neutral_name(raw):
    return len(clean_name(raw)) < NAME_MIN_LENGTH


def neutral_name(profile_id):
    """Nom de remplacement : jamais le nom ni l'e-mail du compte (règle 10)."""
    return f'Organisation {str(profile_id)[:8]}'


def converted_name(raw, profile_id):
    cleaned = clean_name(raw)
    return cleaned if len(cleaned) >= NAME_MIN_LENGTH else neutral_name(profile_id)


def name_key(value):
    """Clé de comparaison des collisions : casse et accents ignorés."""
    decomposed = unicodedata.normalize('NFKD', clean_name(value).casefold())
    return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))


def mixes_scripts(value):
    """Vrai si le nom mélange au moins deux des écritures latine, cyrillique et grecque."""
    found = set()
    for ch in value or '':
        if ch.isalpha():
            label = unicodedata.name(ch, '')
            for script in _SCRIPTS:
                if label.startswith(script):
                    found.add(script)
    return len(found) > 1


def is_blocking(sanction_type, is_active, ends_at, now):
    """Vrai si la sanction bloque encore le compte : type bloquant, active, sans échéance ou échéance future.
    Une sanction levée (`is_active` faux), échue ou non bloquante (avertissement) ne compte pas."""
    return bool(is_active) and sanction_type in BLOCKING_SANCTION_TYPES and (ends_at is None or ends_at > now)


def owner_is_suspended(is_active, sanctioned):
    """Règle de l'état initial : propriétaire désactivé OU sous sanction bloquante en cours => `SUSPENDED`."""
    return (not is_active) or bool(sanctioned)
