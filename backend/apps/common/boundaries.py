"""Analyse statique des frontières entre domaines (ADR 0002) : un domaine ne touche pas aux
modèles d'un autre. Utilisée par les tests (`common.tests.DomainBoundariesTests`) sur tous les domaines. import-linter
n'a pas été ajouté : il est redondant (voir ADR 0002, section R3) et ne voit pas les chargements dynamiques.

Détecte, par analyse `ast` (et non par expression régulière) :
- `import apps.x.models`, `import apps.x.models as m` ;
- `from apps.x.models import ...`, `from apps.x.models.sub import ...` ;
- `from apps.x import models` (et `from apps.x import models as m`, parmi plusieurs noms) ;
- `from apps import x` où `x` est un autre domaine (accès indirect à `x.models`) ;
- les imports relatifs qui sortent du domaine (`from ..x.models import ...`, `from .. import x`) ;
- `apps.get_model('x.Model')`, `get_model('x', 'Model')`, `import_string('apps.x.models.Model')`,
  `importlib.import_module('apps.x.models')`, `__import__('apps.x.models')`.
`common` est partagé ; `get_model('identity.User')` (l'utilisateur) reste permis.
"""
import ast
import os

LOADERS = {'get_model', 'import_string', 'import_module', '__import__'}
SHARED = {'common'}


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _strings(node):
    return [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def _resolve(module_parts, node):
    """Chemin absolu (liste de parties) du module visé par un ImportFrom, relatif ou non."""
    if node.level == 0:
        return (node.module or '').split('.') if node.module else []
    package = module_parts[:-1]
    base = package[:len(package) - (node.level - 1)] if node.level > 1 else package
    return base + ((node.module or '').split('.') if node.module else [])


def find_violations(source, label, module_parts, domains):
    """Liste de messages décrivant les accès aux modèles d'un autre domaine dans `source`.

    `module_parts` : chemin du module analysé, ex. ['apps', 'marketplace', 'views'] ;
    `domains` : ensemble des noms de domaines connus."""
    others = set(domains) - {label} - SHARED
    found = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split('.')
                if len(parts) >= 3 and parts[0] == 'apps' and parts[1] in others and parts[2] == 'models':
                    found.append(f'ligne {node.lineno}: import {alias.name}')
        elif isinstance(node, ast.ImportFrom):
            parts = _resolve(module_parts, node)
            if len(parts) >= 2 and parts[0] == 'apps' and parts[1] in others:
                if len(parts) >= 3 and parts[2] == 'models':
                    found.append(f'ligne {node.lineno}: from {"." * node.level}{node.module or ""} import ...')
                elif len(parts) == 2 and any(alias.name == 'models' for alias in node.names):
                    found.append(f'ligne {node.lineno}: from {".".join(parts)} import models')
            elif parts == ['apps']:
                for alias in node.names:
                    if alias.name in others:
                        found.append(f'ligne {node.lineno}: from apps import {alias.name}')
        elif isinstance(node, ast.Call) and _call_name(node) in LOADERS:
            strings = _strings(node)
            if not strings:
                continue
            target = strings[0].split('.')
            if _call_name(node) == 'get_model':
                other = target[0]
                model = target[1] if len(target) > 1 else (strings[1] if len(strings) > 1 else '')
                if other in others and not (other == 'identity' and model.lower() == 'user'):
                    found.append(f'ligne {node.lineno}: get_model({strings[0]!r})')
            elif len(target) >= 3 and target[0] == 'apps' and target[1] in others and target[2] == 'models':
                found.append(f'ligne {node.lineno}: {_call_name(node)}({strings[0]!r})')
    return found


def scan_domain(apps_root, label, domains, skip_tests=True):
    """Analyse tous les modules (hors migrations et, par défaut, tests) du domaine `label`."""
    offenders = []
    base = os.path.join(apps_root, label)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('migrations', '__pycache__')]
        for name in files:
            if not name.endswith('.py') or (skip_tests and name.startswith('tests')):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, os.path.dirname(apps_root)).replace(os.sep, '/')
            parts = rel[:-3].split('/')
            if parts[-1] == '__init__':
                parts = parts[:-1] + ['__init__']
            with open(path, encoding='utf-8') as handle:
                for message in find_violations(handle.read(), label, parts, domains):
                    offenders.append(f'{rel}: {message}')
    return offenders
