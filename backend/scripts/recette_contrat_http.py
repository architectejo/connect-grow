"""Recette du contrat front <-> backend (lot 0) : rejoue en HTTP les parcours clés contre un
serveur réel et compare chaque réponse aux types de `connect-grow/src/api/types.ts`.

Outil de recette, jamais lancé par `manage.py test`. Prérequis : un serveur lancé sur une base
SQLite jetable (migrate, setup_roles, seed_catalog), avec DEBUG=True, NUM_PROXIES=1 et la
journalisation INFO activée (le code OTP n'est visible que dans le journal du serveur).

    python scripts/recette_contrat_http.py http://127.0.0.1:8765 <journal_serveur> <dossier_backend>

Chaque écart est imprimé avec le préfixe `ECART` ; les étapes réussies avec `OK`.
"""
import io
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8765'
LOG = sys.argv[2] if len(sys.argv) > 2 else 'server.log'
BACKEND_DIR = sys.argv[3] if len(sys.argv) > 3 else '.'
API = BASE + '/api/'
RUN = uuid.uuid4().hex[:6]
FINDINGS = []
_IP_COUNTER = [10]


def finding(msg):
    FINDINGS.append(msg)
    print('ECART', msg)


def ok(msg):
    print('OK   ', msg)


# --- HTTP -----------------------------------------------------------------------------

class Resp:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.raw = status, headers, body
        try:
            self.json = json.loads(body) if body else None
        except ValueError:
            self.json = None

    def __repr__(self):
        return f"<{self.status} {self.raw[:200]!r}>"


def fresh_ip():
    _IP_COUNTER[0] += 1
    return f"10.77.{_IP_COUNTER[0] // 250}.{_IP_COUNTER[0] % 250}"


def call(method, path, body=None, token=None, files=None, form=None, ip=None, params=None, headers=None):
    url = API + path
    if params:
        url += '?' + '&'.join(f"{k}={v}" for k, v in params.items())
    hdr = {'X-Forwarded-For': ip or fresh_ip()}
    data = None
    if files is not None or form is not None:
        boundary = '----recette' + uuid.uuid4().hex
        buf = io.BytesIO()
        for k, v in (form or {}).items():
            buf.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for k, (name, content, ctype) in (files or {}).items():
            buf.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                      f'Content-Type: {ctype}\r\n\r\n'.encode() + content + b'\r\n')
        buf.write(f'--{boundary}--\r\n'.encode())
        data = buf.getvalue()
        hdr['Content-Type'] = f'multipart/form-data; boundary={boundary}'
    elif body is not None:
        data = json.dumps(body).encode()
        hdr['Content-Type'] = 'application/json'
    if token:
        hdr['Authorization'] = f'Bearer {token}'
    hdr.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req) as r:
            return Resp(r.status, dict(r.headers), r.read())
    except urllib.error.HTTPError as e:
        return Resp(e.code, dict(e.headers), e.read())


def expect(label, resp, status, code=None):
    good = resp.status == status
    if good and code is not None:
        good = isinstance(resp.json, dict) and resp.json.get('code') == code
    if good:
        ok(f"{label} -> {resp.status}" + (f" ({code})" if code else ''))
    else:
        finding(f"{label} : attendu {status}{' / ' + code if code else ''}, obtenu {resp!r}")
    return good


# --- Contrôle de type (miroir de types.ts) ---------------------------------------------

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
DATE_RE = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$')


def _kind_ok(value, kind):
    if kind == 'null':
        return value is None
    if kind == 'str':
        return isinstance(value, str)
    if kind == 'uuid':
        return isinstance(value, str) and bool(UUID_RE.match(value))
    if kind == 'date':
        return isinstance(value, str) and bool(DATE_RE.match(value))
    if kind == 'num':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == 'bool':
        return isinstance(value, bool)
    if kind == 'list':
        return isinstance(value, list)
    if kind == 'obj':
        return isinstance(value, dict)
    raise ValueError(kind)


def check_shape(label, obj, spec):
    """spec : {clé: 'type|type'} ; suffixe `?` = clé optionnelle dans types.ts. `null` doit être
    cité pour être accepté (TS non nullable sinon)."""
    if not isinstance(obj, dict):
        finding(f"{label} : objet attendu, obtenu {type(obj).__name__}")
        return
    bad = 0
    for raw_key, kinds in spec.items():
        optional = raw_key.endswith('?')
        key = raw_key.rstrip('?')
        if key not in obj:
            if not optional:
                finding(f"{label} : clé requise absente `{key}`")
                bad += 1
            continue
        if not any(_kind_ok(obj[key], k) for k in kinds.split('|')):
            finding(f"{label} : `{key}` = {obj[key]!r} ne correspond pas à TS `{kinds}`")
            bad += 1
    extra = sorted(set(obj) - {k.rstrip('?') for k in spec})
    if extra:
        print(f"INFO  {label} : clés absentes de types.ts : {extra}")
    if not bad:
        ok(f"{label} : conforme à types.ts")


SPEC_USER = {
    'id': 'uuid', 'email': 'str', 'full_name': 'str', 'photo?': 'str|null', 'user_type': 'str',
    'phone?': 'str', 'ville?': 'uuid|null', 'ville_name?': 'str', 'commune?': 'uuid|null',
    'commune_name?': 'str', 'business_profile?': 'obj|null', 'date_joined?': 'date', 'phone_verified?': 'bool',
}
SPEC_SELLER = {
    'id': 'uuid', 'full_name': 'str', 'photo?': 'str|null', 'user_type': 'str',
    'business_profile?': 'obj|null', 'date_joined?': 'date',
}
SPEC_RATING = {'average': 'num|null', 'count': 'num'}
SPEC_POST = {
    'id': 'uuid', 'seller': 'obj', 'seller_name?': 'str', 'category': 'uuid', 'category_name?': 'str',
    'commune': 'uuid', 'commune_name?': 'str', 'post_type': 'str', 'title': 'str', 'description': 'str',
    'price': 'str', 'currency?': 'str', 'condition?': 'str|null', 'stock?': 'num',
    'is_price_negotiable?': 'bool', 'is_exchangeable?': 'bool', 'main_image?': 'str|null', 'images?': 'list',
    'is_favorited?': 'bool', 'favorites_count?': 'num', 'views_count': 'num', 'likes_count': 'num',
    'created_at': 'date', 'status?': 'str', 'expires_at?': 'date|null', 'visibility_score?': 'num',
    'visibility_rank?': 'str', 'badges?': 'list', 'is_trending?': 'bool', 'is_sponsored?': 'bool',
    'offer_rating?': 'obj', 'seller_rating?': 'obj', 'shares_count?': 'num',
}
SPEC_REVIEW = {
    'id': 'uuid', 'post': 'uuid|null', 'is_mine': 'bool', 'user_name': 'str', 'offer_rating': 'num',
    'seller_rating': 'num', 'content': 'str', 'source': 'str', 'reply_content?': 'str|null',
    'reply_at?': 'date|null', 'created_at': 'date', 'edited_at?': 'date|null', 'is_post_owner?': 'bool',
    'can_edit?': 'bool', 'contest_report_id?': 'uuid|null', 'contest_responded?': 'bool',
}
SPEC_ELIG = {'can_review': 'bool', 'reason': 'str|null', 'available_at': 'date|null', 'review_id': 'uuid|null'}
SPEC_NOTIF = {
    'id': 'uuid', 'notification_type': 'str', 'title': 'str', 'content': 'str', 'link?': 'str|null',
    'is_read': 'bool', 'created_at': 'date',
}
SPEC_KYC = {
    'id': 'uuid', 'document_type': 'str', 'download_url?': 'str|null', 'status': 'str',
    'rejection_reason?': 'str', 'created_at': 'date', 'reviewed_at?': 'date|null',
}
SPEC_BUSINESS = {
    'id': 'uuid', 'business_name': 'str', 'logo?': 'str|null', 'bio?': 'str', 'categories?': 'list',
    'ville_name?': 'str|null', 'commune_name?': 'str|null', 'is_verified': 'bool',
}
SPEC_PAGE = {'count': 'num', 'next': 'str|null', 'previous': 'str|null', 'results': 'list'}
SPEC_FAV = {'id': 'uuid', 'post': 'obj', 'created_at': 'date'}


# --- Base de données (opérations hors API) ---------------------------------------------

def db(code):
    out = subprocess.run(
        [sys.executable, 'manage.py', 'shell', '-c', code], cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-800:])
    return out.stdout.strip()


def read_otp(phone, purpose='REGISTER'):
    time.sleep(0.3)
    text = open(LOG, encoding='utf-8', errors='replace').read()
    found = re.findall(r'\[OTP DEV\] (\S+) pour ' + re.escape(phone) + r' \(' + purpose + r'\)', text)
    return found[-1] if found else None


def jpeg(color=(200, 30, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (40, 40), color).save(buf, 'JPEG')
    return buf.getvalue()


# --- Parcours --------------------------------------------------------------------------

def main():
    pw = 'Recette-mdp-2026!'
    ip_reg = fresh_ip()

    # 1. Inscription par OTP (téléphone) d'un vendeur ENTREPRISE
    phone = '+2438' + RUN.translate(str.maketrans('abcdef', '123456')).ljust(8, '0')[:8]
    r = call('POST', 'accounts/otp/request/', {'phone': phone, 'purpose': 'REGISTER'}, ip=ip_reg)
    expect('OTP request', r, 200)
    check_shape('OTP request', r.json, {'message': 'str', 'expires_in_minutes': 'num'})
    code = read_otp(phone)
    if not code:
        finding("OTP : le code n'apparait pas dans le journal serveur (logger apps.identity.sms au niveau INFO "
                "non configuré par settings.py ?) - inscription par téléphone impossible en recette locale")
        return
    r = call('POST', 'accounts/register/', {
        'full_name': 'Sandrine Mbala', 'password': pw, 'user_type': 'ENTREPRISE', 'phone': phone,
        'otp_code': code, 'business_profile': {'business_name': f'Atelier {RUN}'},
    }, ip=ip_reg)
    expect('register téléphone+OTP (ENTREPRISE)', r, 201)
    if r.status != 201:
        return
    check_shape('register -> User', r.json, SPEC_USER)
    if 'password' in r.json or 'otp_code' in r.json:
        finding('register expose password/otp_code')
    seller_id = r.json['id']

    # Mauvais OTP, rejeu du même code
    r = call('POST', 'accounts/register/', {'full_name': 'X', 'password': pw, 'phone': phone, 'otp_code': code})
    expect('register rejeu du code OTP', r, 400)

    # Acheteurs par e-mail (sans téléphone : email non nul, phone null)
    emails = [f'acheteur{i}.{RUN}@example.com' for i in (1, 2, 3)]
    buyer_ids = []
    for i, em in enumerate(emails):
        r = call('POST', 'accounts/register/', {'full_name': f'Acheteur Numéro{i}', 'password': pw, 'email': em,
                                                'user_type': 'PARTICULIER'})
        expect(f'register e-mail {i}', r, 201)
        buyer_ids.append(r.json['id'])
        if i == 0:
            check_shape('register e-mail -> User', r.json, SPEC_USER)
    r = call('POST', 'accounts/register/', {'full_name': 'Doublon', 'password': pw, 'email': emails[0]})
    expect('register e-mail déjà pris', r, 400)

    # 2. Connexion, profil, refresh, logout, logout-all
    r = call('POST', 'accounts/login/', {'phone': phone, 'password': pw})
    expect('login téléphone', r, 200)
    check_shape('login', r.json, {'access': 'str', 'refresh': 'str'})
    s_access, s_refresh = r.json['access'], r.json['refresh']
    r = call('POST', 'accounts/login/', {'email': emails[0], 'password': pw})
    b_access, b_refresh = r.json['access'], r.json['refresh']
    r = call('POST', 'accounts/login/', {'email': emails[1], 'password': pw})
    b2_access = r.json['access']
    r = call('POST', 'accounts/login/', {'email': emails[2], 'password': pw})
    b3_access = r.json['access']
    r = call('POST', 'accounts/login/', {'email': emails[0], 'password': 'mauvais-mot-de-passe'})
    expect('login mauvais mot de passe', r, 401)
    print('INFO  corps 401 login :', r.json)

    r = call('GET', 'accounts/me/', token=s_access)
    expect('me vendeur', r, 200)
    check_shape('me (ENTREPRISE)', r.json, SPEC_USER)
    check_shape('me.business_profile', r.json.get('business_profile'),
                {'business_name': 'str', 'categories?': 'list', 'bio?': 'str', 'logo?': 'str|null', 'nif?': 'str',
                 'is_verified?': 'bool'})
    r = call('GET', 'accounts/me/', token=b_access)
    check_shape('me (PARTICULIER par e-mail)', r.json, SPEC_USER)
    r = call('GET', 'accounts/me/')
    expect('me sans jeton', r, 401)
    print('INFO  corps 401 :', r.json)
    r = call('GET', 'accounts/me/', token='pas.un.jeton')
    expect('me jeton invalide', r, 401)

    r = call('PATCH', 'accounts/me/', {'full_name': 'Sandrine M. Mbala'}, token=s_access)
    expect('PATCH me full_name', r, 200)
    r = call('PATCH', 'accounts/me/', {'password': 'AutreMdp-2026!!'}, token=s_access)
    expect('PATCH me password refusé', r, 400)
    r = call('PATCH', 'accounts/me/', {'business_profile': {'is_verified': True}}, token=s_access)
    r2 = call('GET', 'accounts/me/', token=s_access)
    if r2.json['business_profile'].get('is_verified'):
        finding("BLOQUANT règle 3 : is_verified modifiable par l'utilisateur via PATCH /me/")
    else:
        ok("is_verified non modifiable via PATCH /me/")

    # refresh : rotation + rejeu de l'ancien jeton
    r = call('POST', 'accounts/token/refresh/', {'refresh': b_refresh})
    expect('refresh', r, 200)
    check_shape('refresh', r.json, {'access': 'str', 'refresh': 'str'})
    new_refresh = r.json['refresh']
    r = call('POST', 'accounts/token/refresh/', {'refresh': b_refresh})
    expect('refresh rejeu (rotation)', r, 401)
    r = call('POST', 'accounts/logout/', {'refresh': new_refresh})
    expect('logout', r, 200)
    r = call('POST', 'accounts/token/refresh/', {'refresh': new_refresh})
    expect('refresh après logout', r, 401)
    r = call('POST', 'accounts/logout/', {})
    expect('logout sans refresh', r, 400)
    r = call('POST', 'accounts/login/', {'email': emails[0], 'password': pw})
    b_access, b_refresh = r.json['access'], r.json['refresh']
    r = call('POST', 'accounts/login/', {'email': emails[0], 'password': pw})
    other_refresh = r.json['refresh']
    r = call('POST', 'accounts/logout-all/', {'refresh': b_refresh}, token=b_access)
    expect('logout-all', r, 200)
    check_shape('logout-all', r.json, {'message': 'str', 'revoked': 'num'})
    r = call('POST', 'accounts/token/refresh/', {'refresh': other_refresh})
    expect('refresh après logout-all', r, 401)
    r = call('POST', 'accounts/login/', {'email': emails[0], 'password': pw})
    b_access = r.json['access']

    # 3. Catalogue + offre avec image
    cities = call('GET', 'marketplace/cities/').json
    commune = cities[0]['communes'][0]['id']
    commune2 = cities[0]['communes'][1]['id']
    cats = call('GET', 'marketplace/categories/').json
    check_shape('category', cats[0], {'id': 'uuid', 'name': 'str', 'icon?': 'str', 'slug': 'str'})
    check_shape('city', cities[0], {'id': 'uuid', 'name': 'str', 'communes': 'list'})
    check_shape('commune', cities[0]['communes'][0], {'id': 'uuid', 'name': 'str', 'city': 'uuid'})
    cat = cats[0]['id']

    def offer_form(title, price='25.50'):
        return {'post_type': 'PRODUIT', 'category': cat, 'title': title, 'description': 'Description de test suffisamment longue pour passer',
                'price': price, 'currency': 'USD', 'is_price_negotiable': 'false', 'is_exchangeable': 'true',
                'commune': commune, 'condition': 'NEUF', 'stock': '3'}

    r = call('POST', 'marketplace/posts/', form=offer_form(f'Perceuse {RUN}'), files={'main_image': ('a.jpg', jpeg(), 'image/jpeg')},
             token=s_access)
    expect('création offre avec image', r, 201)
    if r.status != 201:
        return
    check_shape('Post (création)', r.json, SPEC_POST)
    check_shape('Post.seller', r.json['seller'], SPEC_SELLER)
    offer_id = r.json['id']
    r = call('POST', 'marketplace/posts/', form=offer_form(f'Sans image {RUN}'), token=s_access)
    expect('création offre sans image', r, 400)
    r = call('POST', 'marketplace/posts/', form=offer_form(f'Prix {RUN}', '-5'), files={'main_image': ('a.jpg', jpeg(), 'image/jpeg')}, token=s_access)
    print('INFO  prix négatif ->', r.status, r.raw[:120])
    r = call('POST', 'marketplace/posts/', form=offer_form(f'Fausse image {RUN}'), files={'main_image': ('a.jpg', b'GIF89a-not-an-image', 'image/jpeg')}, token=s_access)
    expect('création offre image invalide', r, 400)
    r = call('POST', f'marketplace/posts/{offer_id}/images/', files={'image': ('g.jpg', jpeg((10, 200, 10)), 'image/jpeg')}, token=s_access)
    expect('galerie : ajout', r, 201)
    check_shape('PostImage', r.json[0], {'id': 'uuid', 'image': 'str', 'order?': 'num'})
    r = call('POST', f'marketplace/posts/{offer_id}/images/', files={'image': ('g.jpg', jpeg(), 'image/jpeg')}, token=b_access)
    expect('galerie : ajout par un tiers', r, 404)
    img_id = call('GET', f'marketplace/posts/{offer_id}/').json['images'][0]['id']
    r = call('DELETE', f'marketplace/posts/{offer_id}/images/', params={'image_id': img_id}, token=s_access)
    expect('galerie : suppression', r, 204)

    # Offres supplémentaires pour pagination/tri
    for k in range(3):
        call('POST', 'marketplace/posts/', form=offer_form(f'Annexe {k} {RUN}', str(10 + k)), files={'main_image': ('a.jpg', jpeg(), 'image/jpeg')}, token=s_access)

    # 4. Liste / détail
    r = call('GET', 'marketplace/posts/')
    expect('liste offres anonyme', r, 200)
    page = r.json
    if isinstance(page, dict):
        check_shape('liste offres (paginée)', page, SPEC_PAGE)
        results = page['results']
    else:
        print('INFO  liste offres : tableau non paginé (unwrapList)')
        results = page
    check_shape('Post (liste)', results[0], SPEC_POST)
    check_shape('offer_rating', results[0]['offer_rating'], SPEC_RATING)
    check_shape('seller_rating', results[0]['seller_rating'], SPEC_RATING)
    for key in ('phone', 'email', 'nif'):
        if key in results[0]['seller']:
            finding(f"BLOQUANT règle 10 : `{key}` exposé dans seller de la liste d'offres")
    r = call('GET', f'marketplace/posts/{offer_id}/')
    expect('détail offre anonyme', r, 200)
    check_shape('Post (détail)', r.json, SPEC_POST)
    if 'is_hidden_by_moderation' in r.json:
        finding("`is_hidden_by_moderation` visible d'un anonyme (devrait être réservé au vendeur)")
    r = call('GET', f'marketplace/posts/{offer_id}/', token=s_access)
    if 'is_hidden_by_moderation' in r.json:
        print('INFO  is_hidden_by_moderation visible du vendeur (attendu), absent de types.ts')
    expect('détail offre id inconnu', call('GET', f'marketplace/posts/{uuid.uuid4()}/'), 404)
    expect('détail offre id invalide', call('GET', 'marketplace/posts/pas-un-uuid/'), 404)
    r = call('GET', 'marketplace/posts/', params={'ordering': '-visibility_score', 'near': 'pas-un-uuid', 'price_min': 'abc'})
    print('INFO  filtre price_min=abc ->', r.status)
    r = call('GET', 'marketplace/posts/', params={'page': '999'})
    print('INFO  page=999 ->', r.status, (r.json or {}).get('detail') if isinstance(r.json, dict) else '')

    # 5. Favori
    r = call('POST', f'marketplace/posts/{offer_id}/favorite/', token=b_access)
    expect('favori (ajout)', r, 200)
    check_shape('favorite toggle', r.json, {'favorited': 'bool'})
    r = call('GET', f'marketplace/posts/{offer_id}/', token=b_access)
    if not r.json.get('is_favorited') or r.json.get('favorites_count') != 1:
        finding(f"détail après favori : is_favorited/favorites_count incohérents {r.json.get('is_favorited')} {r.json.get('favorites_count')}")
    r = call('GET', 'marketplace/favorites/', token=b_access)
    expect('liste favoris', r, 200)
    favs = r.json['results'] if isinstance(r.json, dict) else r.json
    check_shape('Favorite', favs[0], SPEC_FAV)
    expect('favori anonyme', call('POST', f'marketplace/posts/{offer_id}/favorite/'), 401)
    expect('favori (retrait)', call('POST', f'marketplace/posts/{offer_id}/favorite/', token=b_access), 200)

    # 6. Contact, éligibilité, avis
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}, token=b_access)
    expect('éligibilité sans contact', r, 200)
    check_shape('éligibilité', r.json, SPEC_ELIG)
    if r.json['reason'] != 'no_contact':
        finding(f"éligibilité sans contact : reason={r.json['reason']} (attendu no_contact)")
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}, token=s_access)
    if r.json.get('reason') != 'own_offer':
        finding(f"éligibilité propre offre : {r.json}")
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': 'zzz'}, token=b_access)
    expect('éligibilité post invalide', r, 400)
    print('INFO  corps 400 éligibilité :', r.json)
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': str(uuid.uuid4())}, token=b_access)
    expect('éligibilité offre inconnue', r, 404, 'offer_not_found')
    expect('éligibilité anonyme', call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}), 401)

    for tok, who in ((b_access, 'B1'), (b2_access, 'B2'), (b3_access, 'B3')):
        r = call('POST', 'interactions/contacts/', {'post': offer_id, 'message': f'Bonjour, ceci est un message de {who}'}, token=tok)
        expect(f'contact {who}', r, 201)
        if who == 'B1':
            check_shape('ContactEvent', r.json, {'id': 'uuid', 'post': 'uuid', 'sender': 'uuid', 'sender_name': 'str', 'message': 'str', 'created_at': 'date'})
    r = call('POST', 'interactions/contacts/', {'post': offer_id, 'message': 'Doublon dans la fenêtre'}, token=b_access)
    expect('contact en double', r, 400)
    print('INFO  corps doublon contact :', r.json)
    r = call('POST', 'interactions/contacts/', {'post': offer_id, 'message': 'Mon propre bien'}, token=s_access)
    expect('contact sur sa propre offre', r, 400)
    expect('contact anonyme', call('POST', 'interactions/contacts/', {'post': offer_id, 'message': 'x'}), 401)
    expect('contact message vide', call('POST', 'interactions/contacts/', {'post': offer_id, 'message': ''}, token=b3_access), 400)

    r = call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}, token=b_access)
    check_shape('éligibilité après contact', r.json, SPEC_ELIG)
    print('INFO  éligibilité juste après contact :', r.json)
    if r.json['reason'] != 'too_early':
        finding(f"éligibilité juste après contact : reason={r.json['reason']} attendu too_early")
    r = call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 5, 'seller_rating': 5, 'content': 'Excellent service vraiment'}, token=b_access)
    expect('avis trop tôt', r, 403, 'review_too_early')
    print('INFO  corps review_too_early :', r.json)

    # Réglages : fenêtre 1 h ; contact antidaté de 2 h ; compte récent d'abord (account_too_new)
    db("from apps.reviews.models import ReviewSettings as S; s=S.get_solo(); s.delay_after_contact_hours=1; "
       "s.min_account_age_hours=24; s.min_reviews_to_display=2; s.save(); "
       "from apps.marketplace.models import ContactEvent as C; "
       "from django.utils import timezone as t; from datetime import timedelta as d; "
       "C.objects.update(created_at=t.now()-d(hours=2))")
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}, token=b_access)
    print('INFO  éligibilité contact ancien, compte récent :', r.json)
    if r.json.get('reason') != 'account_too_new':
        finding(f"éligibilité compte récent : reason={r.json.get('reason')} attendu account_too_new")
    else:
        check_shape('éligibilité account_too_new', r.json, SPEC_ELIG)
        if not r.json.get('available_at'):
            finding('account_too_new sans available_at')
    db("from apps.reviews.models import ReviewSettings as S; s=S.get_solo(); s.min_account_age_hours=0; s.save()")
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}, token=b_access)
    check_shape('éligibilité can_review', r.json, SPEC_ELIG)
    if not r.json['can_review']:
        finding(f"éligibilité attendue vraie : {r.json}")

    # Notation invalide
    for bad in ({'offer_rating': 0, 'seller_rating': 5, 'content': 'Contenu correct ici'},
                {'offer_rating': 5, 'seller_rating': 6, 'content': 'Contenu correct ici'},
                {'offer_rating': 5, 'seller_rating': 5, 'content': 'court'},
                {'offer_rating': 'x', 'seller_rating': 5, 'content': 'Contenu correct ici'}):
        expect(f'avis invalide {list(bad.values())[:2]}', call('POST', 'interactions/reviews/', {'post': offer_id, **bad}, token=b_access), 400)
    r = call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 4, 'seller_rating': 5, 'content': 'Très bon vendeur, rapide.'}, token=b_access)
    expect('avis créé (B1)', r, 201)
    check_shape('Review (création)', r.json, SPEC_REVIEW)
    r1 = r.json
    if not r1['is_mine'] or not r1['can_edit']:
        finding(f"Review création : is_mine/can_edit attendus vrais {r1['is_mine']} {r1['can_edit']}")
    if r1['user_name'] != 'Acheteur N.':
        print('INFO  user_name =', r1['user_name'])
    expect('avis en double', call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 4, 'seller_rating': 5, 'content': 'Un deuxième avis'}, token=b_access), 409, 'already_reviewed')
    expect('avis sur sa propre offre', call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 4, 'seller_rating': 5, 'content': 'Mon avis perso ok'}, token=s_access), 403, 'own_offer')
    expect('avis anonyme', call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 4, 'seller_rating': 5, 'content': 'Anonyme sans compte'}), 401)

    # Note masquée sous le seuil (min 2) puis visible
    d = call('GET', f'marketplace/posts/{offer_id}/').json
    if d['offer_rating'] != {'average': None, 'count': 1}:
        finding(f"offer_rating sous le seuil attendu {{average:null,count:1}}, obtenu {d['offer_rating']}")
    else:
        ok('offer_rating sous le seuil : average null, count 1')
    r = call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 2, 'seller_rating': 3, 'content': 'Moyen, livraison tardive.'}, token=b2_access)
    expect('avis créé (B2)', r, 201)
    r2 = r.json
    d = call('GET', f'marketplace/posts/{offer_id}/').json
    if d['offer_rating'] != {'average': 3.0, 'count': 2} or d['seller_rating'] != {'average': 4.0, 'count': 2}:
        finding(f"moyennes après 2 avis : offer {d['offer_rating']} seller {d['seller_rating']} (attendu 3.0/4.0, 2)")
    else:
        ok('moyennes offer 3.0 / seller 4.0 sur 2 avis')

    # Liste d'avis publique : is_mine, pas d'identifiant d'auteur
    r = call('GET', 'interactions/reviews/', params={'post': offer_id})
    expect('liste avis anonyme', r, 200)
    items = r.json['results'] if isinstance(r.json, dict) else r.json
    for it in items:
        check_shape('Review (liste)', it, SPEC_REVIEW)
        if it['is_mine'] or it.get('contest_report_id'):
            finding('liste anonyme : is_mine/contest_report_id non faux')
        for banned in ('user', 'user_id', 'author', 'contact_channel', 'contact_event_id', 'seller_context_id'):
            if banned in it:
                finding(f"règle 10 : `{banned}` exposé dans la liste publique des avis")
    r = call('GET', 'interactions/reviews/', params={'post': offer_id}, token=b_access)
    mine = [x for x in (r.json['results'] if isinstance(r.json, dict) else r.json) if x['is_mine']]
    if len(mine) != 1:
        finding(f'liste avis connecté B1 : is_mine attendu 1, obtenu {len(mine)}')

    # Modification / suppression / autre auteur
    r = call('PATCH', f"interactions/reviews/{r1['id']}/", {'content': 'Très bon vendeur, vraiment rapide.', 'offer_rating': 5}, token=b_access)
    expect('avis modifié', r, 200)
    check_shape('Review (modifié)', r.json, SPEC_REVIEW)
    if not r.json.get('edited_at'):
        finding('edited_at non renseigné après modification')
    expect('avis modifié par un tiers', call('PATCH', f"interactions/reviews/{r1['id']}/", {'content': 'Piratage du contenu !'}, token=b2_access), 403, 'not_author')
    expect('avis PATCH vide', call('PATCH', f"interactions/reviews/{r1['id']}/", {}, token=b_access), 400)
    expect('avis modifié par le vendeur', call('PATCH', f"interactions/reviews/{r1['id']}/", {'content': 'Le vendeur modifie !!'}, token=s_access), 403, 'not_author')
    r = call('DELETE', f"interactions/reviews/{r1['id']}/", token=b_access)
    expect('avis supprimé (B1)', r, 204)
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}, token=b_access)
    if r.json.get('reason') != 'recently_deleted':
        finding(f"éligibilité après suppression : {r.json} (attendu recently_deleted)")
    else:
        ok('éligibilité recently_deleted après suppression')
    expect('ré-écriture après suppression', call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 1, 'seller_rating': 1, 'content': 'Je me venge avec un nouvel avis'}, token=b_access), 409, 'review_recently_deleted')

    # B3 écrit un avis ; réponse du vendeur
    r = call('POST', 'interactions/reviews/', {'post': offer_id, 'offer_rating': 1, 'seller_rating': 1, 'content': 'Article jamais reçu, vendeur absent.'}, token=b3_access)
    expect('avis créé (B3)', r, 201)
    r3 = r.json
    expect('réponse par un tiers', call('POST', f"interactions/reviews/{r3['id']}/reply/", {'reply_content': 'Je ne suis pas le vendeur'}, token=b_access), 403, 'not_seller')
    r = call('POST', f"interactions/reviews/{r3['id']}/reply/", {'reply_content': 'Je conteste, merci de me contacter.'}, token=s_access)
    expect('réponse du vendeur', r, 200)
    check_shape('Review (réponse)', r.json, SPEC_REVIEW)
    if not r.json.get('is_post_owner'):
        finding('is_post_owner faux pour le vendeur')
    expect('seconde réponse', call('POST', f"interactions/reviews/{r3['id']}/reply/", {'reply_content': 'Encore une'}, token=s_access), 409, 'already_replied')
    expect('modif après réponse', call('PATCH', f"interactions/reviews/{r3['id']}/", {'content': 'Je réécris après coup'}, token=b3_access), 403, 'review_locked_after_reply')
    expect('suppression après réponse', call('DELETE', f"interactions/reviews/{r3['id']}/", token=b3_access), 403, 'review_locked_after_reply')
    expect('réponse vide', call('POST', f"interactions/reviews/{r2['id']}/reply/", {'reply_content': ''}, token=s_access), 400)

    # 7. Signalement CONTACT_FICTIF (B2 : pas de réponse du vendeur, auteur modifiable)
    expect('signalement contact fictif par un tiers', call('POST', 'moderation/reports/', {'target_type': 'REVIEW', 'object_id': r2['id'], 'reason': 'CONTACT_FICTIF'}, token=b_access), 403, 'not_seller')
    r = call('POST', 'moderation/reports/', {'target_type': 'REVIEW', 'object_id': r2['id'], 'reason': 'CONTACT_FICTIF', 'description': 'Je ne connais pas cette personne.'}, token=s_access)
    expect('signalement contact fictif (vendeur)', r, 201)
    print('INFO  corps signalement (non modérateur) :', r.json)
    for banned in ('reporter_name', 'decision_notes', 'assigned_to_name'):
        if r.json and banned in r.json:
            finding(f"signalement : `{banned}` visible du signaleur non modérateur")
    expect('signalement en double', call('POST', 'moderation/reports/', {'target_type': 'REVIEW', 'object_id': r2['id'], 'reason': 'CONTACT_FICTIF'}, token=s_access), 409)
    r = call('GET', 'interactions/reviews/', params={'post': offer_id}, token=b2_access)
    mine = [x for x in (r.json['results'] if isinstance(r.json, dict) else r.json) if x['is_mine']][0]
    check_shape('Review (auteur contesté)', mine, SPEC_REVIEW)
    print('INFO  can_delete / can_edit auteur contesté :', mine.get('can_delete'), mine.get('can_edit'))
    if not mine.get('contest_report_id'):
        finding('auteur contesté : contest_report_id absent alors qu\'un signalement CONTACT_FICTIF est ouvert')
        return
    report_id = mine['contest_report_id']
    # Un tiers ne voit pas le signalement
    r = call('GET', 'interactions/reviews/', params={'post': offer_id}, token=s_access)
    seen = [x for x in (r.json['results'] if isinstance(r.json, dict) else r.json) if x['id'] == r2['id']][0]
    if seen.get('contest_report_id'):
        finding("règle 10 : contest_report_id exposé au vendeur signaleur / tiers")
    expect('recours par un tiers', call('POST', f'moderation/reports/{report_id}/author-response/', {'author_response': 'Ce n\'est pas mon avis'}, token=b_access), 404)
    expect('recours par le vendeur', call('POST', f'moderation/reports/{report_id}/author-response/', {'author_response': 'je suis le vendeur'}, token=s_access), 404)
    expect('recours vide', call('POST', f'moderation/reports/{report_id}/author-response/', {'author_response': ''}, token=b2_access), 400)
    r = call('POST', f'moderation/reports/{report_id}/author-response/', {'author_response': 'Voici ma preuve : capture de la conversation.'}, token=b2_access)
    expect('recours de l\'auteur', r, 200)
    check_shape('AuthorResponseResult', r.json, {'id': 'uuid', 'status': 'str', 'author_responded_at': 'date'})
    expect('recours en double', call('POST', f'moderation/reports/{report_id}/author-response/', {'author_response': 'Encore'}, token=b2_access), 409, 'already_responded')
    r = call('GET', 'interactions/reviews/', params={'post': offer_id}, token=b2_access)
    mine = [x for x in (r.json['results'] if isinstance(r.json, dict) else r.json) if x['is_mine']][0]
    if not mine.get('contest_responded'):
        finding('contest_responded faux après le recours')
    expect('suppression avis contesté', call('DELETE', f"interactions/reviews/{r2['id']}/", token=b2_access), 403, 'review_locked')

    # 8. Modérateur : prise en charge et décision
    mod_email = f'moderateur.{RUN}@example.com'
    db(f"from apps.identity.models import User; from django.contrib.auth.models import Group; "
       f"u=User.objects.create_user(email='{mod_email}', password='{pw}', full_name='Modo Test'); "
       f"u.groups.add(Group.objects.get(name='Modérateur')); print('ok')")
    mod = call('POST', 'accounts/login/', {'email': mod_email, 'password': pw}).json['access']
    expect('file de modération (simple utilisateur)', call('GET', 'moderation/reports/', token=b_access), 403)
    r = call('GET', 'moderation/reports/', token=mod)
    expect('file de modération', r, 200)
    expect('claim', call('POST', f'moderation/reports/{report_id}/claim/', token=mod), 200)
    r = call('POST', f'moderation/reports/{report_id}/resolve/', {'notes': 'Contact non établi.'}, token=mod)
    expect('décision resolve', r, 200)
    print('INFO  statut après décision :', (r.json or {}).get('status'))
    expect('décision rejouée', call('POST', f'moderation/reports/{report_id}/resolve/', {'notes': 'bis'}, token=mod), 409)
    d = call('GET', f'marketplace/posts/{offer_id}/').json
    print('INFO  notes après masquage de l\'avis B2 :', d['offer_rating'], d['seller_rating'])
    if d['offer_rating']['count'] != 1:
        finding(f"avis masqué encore compté : {d['offer_rating']}")
    r = call('GET', 'interactions/reviews/eligibility/', params={'post': offer_id}, token=b2_access)
    if r.json.get('reason') != 'contact_rejected':
        finding(f"éligibilité après masquage : {r.json} (attendu contact_rejected)")
    else:
        ok('éligibilité contact_rejected après décision')
    items = call('GET', 'interactions/reviews/', params={'post': offer_id}).json
    items = items['results'] if isinstance(items, dict) else items
    if any(x['id'] == r2['id'] for x in items):
        finding('avis masqué toujours dans la liste publique')
    expect('modif avis masqué par son auteur', call('PATCH', f"interactions/reviews/{r2['id']}/", {'content': 'Modification après masquage'}, token=b2_access), 403, 'review_locked')

    # 9. Entreprises : pagination et filtre is_verified
    db("from apps.identity.models import User, BusinessProfile\n"
       f"for i in range(24):\n"
       f"    u=User.objects.create_user(email='ent{{}}.{RUN}@example.com'.format(i), password='x', full_name='Ent %d' % i, user_type='ENTREPRISE')\n"
       f"    BusinessProfile.objects.create(user=u, business_name='Zbiz {RUN} %02d' % i, is_verified=(i%3==0))")
    r = call('GET', 'accounts/businesses/', params={'search': f'Zbiz+{RUN}'})
    expect('entreprises page 1', r, 200)
    check_shape('Paginated<PublicBusiness>', r.json, SPEC_PAGE)
    print('INFO  entreprises count/next:', r.json['count'], r.json['next'])
    check_shape('PublicBusiness', r.json['results'][0], SPEC_BUSINESS)
    if len(r.json['results']) != 20 or r.json['count'] != 24 or not r.json['next']:
        finding(f"pagination entreprises : {len(r.json['results'])} résultats, count {r.json['count']}, next {r.json['next']}")
    for banned in ('phone', 'email', 'nif', 'date_joined', 'full_name'):
        if banned in r.json['results'][0]:
            finding(f"règle 10 : `{banned}` exposé par accounts/businesses/")
    r = call('GET', 'accounts/businesses/', params={'search': f'Zbiz+{RUN}', 'page': 2})
    if len(r.json['results']) != 4 or r.json['next'] is not None:
        finding(f"entreprises page 2 : {len(r.json['results'])} résultats, next {r.json['next']}")
    r = call('GET', 'accounts/businesses/', params={'search': f'Zbiz+{RUN}', 'is_verified': 'true'})
    if r.json['count'] != 8 or not all(x['is_verified'] for x in r.json['results']):
        finding(f"filtre is_verified=true : count {r.json['count']} (attendu 8)")
    else:
        ok('filtre is_verified=true : 8 entreprises vérifiées')
    r = call('GET', 'accounts/businesses/', params={'search': f'Zbiz+{RUN}', 'is_verified': 'false'})
    if r.json['count'] != 16:
        finding(f"filtre is_verified=false : count {r.json['count']} (attendu 16)")
    expect('is_verified=peut-etre', call('GET', 'accounts/businesses/', params={'is_verified': 'peut-etre'}), 400)
    r = call('GET', 'accounts/businesses/', params={'page': 99})
    print('INFO  entreprises page=99 ->', r.status, r.raw[:100])

    # 10. KYC
    pdf = b'%PDF-1.4\n% fichier de test\n'
    r = call('POST', 'accounts/kyc/documents/', form={'document_type': 'RCCM'}, files={'file': ('rccm.pdf', pdf, 'application/pdf')}, token=s_access)
    expect('KYC dépôt RCCM', r, 201)
    check_shape('KycDocument', r.json, SPEC_KYC)
    kyc1 = r.json['id']
    if r.json.get('download_url'):
        finding("règle 10 : download_url renvoyé au déposant")
    if 'file' in r.json:
        finding("règle 10 : `file` (chemin) renvoyé dans la réponse KYC")
    expect('KYC doublon de type', call('POST', 'accounts/kyc/documents/', form={'document_type': 'RCCM'}, files={'file': ('r.pdf', pdf, 'application/pdf')}, token=s_access), 400)
    expect('KYC fichier invalide', call('POST', 'accounts/kyc/documents/', form={'document_type': 'ID_NATIONALE'}, files={'file': ('id.pdf', b'MZ-exe', 'application/pdf')}, token=s_access), 400)
    expect('KYC par un particulier', call('POST', 'accounts/kyc/documents/', form={'document_type': 'RCCM'}, files={'file': ('r.pdf', pdf, 'application/pdf')}, token=b_access), 400)
    r = call('GET', 'accounts/kyc/documents/', token=s_access)
    expect('KYC liste', r, 200)
    check_shape('KycDocument (liste)', (r.json['results'] if isinstance(r.json, dict) else r.json)[0], SPEC_KYC)
    expect('KYC liste anonyme', call('GET', 'accounts/kyc/documents/'), 401)
    expect('KYC suppression par un tiers', call('DELETE', f'accounts/kyc/documents/{kyc1}/', token=b_access), 404)
    expect('KYC file de revue (simple utilisateur)', call('GET', 'accounts/kyc/review-queue/', token=s_access), 403)
    expect('KYC téléchargement (simple utilisateur)', call('GET', f'accounts/kyc/documents/{kyc1}/download/', token=s_access), 403)
    r = call('GET', 'accounts/kyc/review-queue/', token=mod)
    expect('KYC file de revue (modérateur)', r, 200)
    q = r.json['results'] if isinstance(r.json, dict) else r.json
    if q:
        check_shape('KycDocument (modérateur)', q[0], {**SPEC_KYC, 'download_url?': 'str'})
    expect('KYC téléchargement (modérateur)', call('GET', f'accounts/kyc/documents/{kyc1}/download/', token=mod), 200)
    expect('KYC suppression', call('DELETE', f'accounts/kyc/documents/{kyc1}/', token=s_access), 204)
    r = call('POST', 'accounts/kyc/documents/', form={'document_type': 'RCCM'}, files={'file': ('rccm.pdf', pdf, 'application/pdf')}, token=s_access)
    kyc2 = r.json['id']
    r = call('POST', f'accounts/kyc/documents/{kyc2}/decision/', {'decision': 'VALIDE'}, token=mod)
    expect('KYC décision VALIDE', r, 200)
    expect('KYC suppression pièce validée', call('DELETE', f'accounts/kyc/documents/{kyc2}/', token=s_access), 400)
    seller_pub = call('GET', f'marketplace/posts/{offer_id}/').json['seller']
    if seller_pub['business_profile']['is_verified']:
        finding("règle 3 : entreprise vérifiée avec une seule pièce validée sur trois")
    for doc_type in ('ID_NATIONALE', 'PIECE_GERANT'):
        r = call('POST', 'accounts/kyc/documents/', form={'document_type': doc_type}, files={'file': ('p.jpg', jpeg(), 'image/jpeg')}, token=s_access)
        expect(f'KYC dépôt {doc_type}', r, 201)
        expect(f'KYC décision {doc_type}', call('POST', f"accounts/kyc/documents/{r.json['id']}/decision/", {'decision': 'VALIDE'}, token=mod), 200)
    seller_pub = call('GET', f'marketplace/posts/{offer_id}/').json['seller']
    if not seller_pub['business_profile']['is_verified']:
        finding("is_verified faux dans seller après validation KYC")
    else:
        ok('seller.business_profile.is_verified vrai après décision KYC')

    # 11. Dispatch outbox puis notifications
    out = subprocess.run([sys.executable, 'manage.py', 'dispatch_outbox'], cwd=BACKEND_DIR, capture_output=True, text=True)
    print('INFO  dispatch_outbox :', out.stdout.strip(), out.stderr.strip()[-200:])
    r = call('GET', 'interactions/notifications/', token=s_access)
    expect('notifications vendeur', r, 200)
    notifs = r.json['results'] if isinstance(r.json, dict) else r.json
    if not notifs:
        finding('aucune notification vendeur après dispatch_outbox')
    else:
        for n in notifs[:3]:
            check_shape('AppNotification', n, SPEC_NOTIF)
        types_seen = sorted({n['notification_type'] for n in notifs})
        print('INFO  types de notification vendeur :', types_seen, 'nb', len(notifs))
    nid = notifs[0]['id']
    r = call('PATCH', f'interactions/notifications/{nid}/', {'is_read': True}, token=s_access)
    expect('notification lue', r, 200)
    expect('notification lue par un tiers', call('PATCH', f'interactions/notifications/{nid}/', {'is_read': True}, token=b_access), 404)
    expect('mark_all_as_read', call('POST', 'interactions/notifications/mark_all_as_read/', token=s_access), 200)
    expect('notifications anonyme', call('GET', 'interactions/notifications/'), 401)
    r = call('GET', 'interactions/conversations/', token=s_access)
    expect('conversations vendeur', r, 200)
    convs = r.json['results'] if isinstance(r.json, dict) else r.json
    print('INFO  conversations vendeur :', len(convs), 'attendu 3')
    if convs:
        print('INFO  clés conversation :', sorted(convs[0].keys()))

    # 12. Dashboard
    r = call('GET', 'marketplace/stats/dashboard/', token=s_access)
    expect('dashboard', r, 200)
    check_shape('DashboardStats', r.json, {'history': 'list', 'summary': 'obj'})
    check_shape('DashboardSummary', r.json['summary'], {
        'total_views': 'num', 'today_views': 'num', 'active_posts': 'num', 'avg_rating': 'num|null',
        'review_count': 'num', 'contacts_count?': 'num', 'contact_rate?': 'num'})

    # 13. Throttles 429 avec Retry-After
    ip = fresh_ip()
    got = None
    for i in range(7):
        r = call('POST', 'accounts/otp/request/', {'phone': f'+24399{RUN.translate(str.maketrans("abcdef","123456"))[:5]}{i}0'}, ip=ip)
        if r.status == 429:
            got = (i + 1, r)
            break
    if not got:
        finding('throttle OTP (5/h par IP) : aucun 429 en 7 requêtes')
    else:
        ra = got[1].headers.get('Retry-After')
        print(f'INFO  429 à la requête {got[0]}, Retry-After={ra}, corps={got[1].json}')
        if not ra or not ra.isdigit():
            finding(f'429 sans Retry-After exploitable : {ra!r}')
        if not isinstance(got[1].json, dict) or 'detail' not in got[1].json:
            finding(f'429 corps inattendu : {got[1].raw[:150]!r}')
        elif 'code' not in got[1].json:
            print('INFO  429 sans clé `code` (detail seul)')
    # Login : échecs répétés
    ip = fresh_ip()
    codes = [call('POST', 'accounts/login/', {'email': emails[1], 'password': f'faux-mdp-{i}'}, ip=ip).status for i in range(8)]
    print('INFO  statuts de 8 échecs de connexion consécutifs :', codes)
    if 429 not in codes:
        finding('limitation des échecs de connexion : aucun 429 en 8 tentatives')
    ip = fresh_ip()
    r = None
    for i in range(12):
        r = call('POST', 'interactions/contacts/', {'post': offer_id, 'message': 'spam spam spam'}, token=b3_access, ip=ip)
    print('INFO  contacts répétés ->', r.status, (r.json or {}))

    print('\nRESUME', len(FINDINGS), 'écart(s)')
    for f in FINDINGS:
        print(' -', f)


if __name__ == '__main__':
    main()
