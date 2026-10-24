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
_STRIPPED_CATEGORIES = {'Cc', 'Cf', 'Zl', 'Zp'}
_SCRIPTS = ('LATIN', 'CYRILLIC', 'GREEK')


def clean_name(raw):
    """Nettoie sans rejeter : caractères Cc/Cf/Zl/Zp retirés, espaces repliés, bords retirés, 255 caractères
    au plus. Pas de NFKC (une marque ne doit pas être modifiée). Peut renvoyer une chaîne vide ou trop courte."""
    text = ''.join(' ' if ch in '\t\n\r' else ch for ch in (raw or ''))
    text = ''.join(ch for ch in text if unicodedata.category(ch) not in _STRIPPED_CATEGORIES)
    return ' '.join(text.split())[:NAME_MAX_LENGTH].strip()


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
