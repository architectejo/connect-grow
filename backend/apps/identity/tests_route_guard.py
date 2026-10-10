"""Garde-fou des routes d'écriture (audit L0-30, ADR 0006 section 6.4).

Toute vue DRF acceptant POST/PUT/PATCH/DELETE doit soit utiliser la brique du contexte actif
(`ActingContextMixin` ou `capability_permission`), soit déclarer `acting_context_exempt = "<raison>"`
(vue toujours personnelle, publique, de modération, etc.).

Les vues existantes sont figées dans `LEGACY_WRITE_ROUTES` (« legacy à migrer en T5 ») : le test échoue
pour toute NOUVELLE vue d'écriture absente de cette liste et sans garde, et il échoue aussi si une entrée
de la liste ne correspond plus à une vue sans garde (vue supprimée, ou migrée sans retirer son entrée).
Quand T5 branche une vue sur la brique, retirer son entrée.
"""
from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.views import APIView

from . import services

WRITE_METHODS = ('post', 'put', 'patch', 'delete')

# Chemin normalisé -> raison. Vues d'écriture existantes sans garde de contexte à la date de T2.
LEGACY_WRITE_ROUTES = {
    'api/accounts/change-password/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/contact-settings/channels/<str:channel>/': 'compte : authentification et réglages toujours personnels',  # PUT
    'api/accounts/contact-settings/phone/': 'compte : authentification et réglages toujours personnels',  # PUT
    'api/accounts/contact-settings/phone/verify/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/kyc/documents/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/kyc/documents/<uuid:pk>/': 'compte : authentification et réglages toujours personnels',  # DELETE
    'api/accounts/kyc/documents/<uuid:pk>/decision/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/login/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/logout-all/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/logout/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/me/': 'compte : authentification et réglages toujours personnels',  # PATCH/PUT
    'api/accounts/otp/request/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/password-reset/confirm/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/register/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/accounts/token/refresh/': 'compte : authentification et réglages toujours personnels',  # POST
    'api/interactions/^contacts/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # POST
    'api/interactions/^contacts/(?P<pk>[^/.]+)/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # DELETE/PATCH/PUT
    'api/interactions/^contacts/reveal/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # POST
    'api/interactions/^exchanges/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # POST
    'api/interactions/^exchanges/(?P<pk>[^/.]+)/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # DELETE/PATCH/PUT
    'api/interactions/^messages/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # POST
    'api/interactions/^messages/(?P<pk>[^/.]+)/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # DELETE/PATCH/PUT
    'api/interactions/^notifications/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # POST
    'api/interactions/^notifications/(?P<pk>[^/.]+)/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # DELETE/PATCH/PUT
    'api/interactions/^notifications/mark_all_as_read/$': 'interactions : acheteur personnel, boîte vendeur à migrer en T5',  # POST
    'api/interactions/^reviews/$': 'avis : acheteur toujours personnel, réponse vendeur à migrer en T5',  # POST
    'api/interactions/^reviews/(?P<pk>[^/.]+)/$': 'avis : acheteur toujours personnel, réponse vendeur à migrer en T5',  # DELETE/PATCH/PUT
    'api/interactions/^reviews/(?P<pk>[^/.]+)/reply/$': 'avis : acheteur toujours personnel, réponse vendeur à migrer en T5',  # POST
    'api/marketplace/^favorites/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^favorites/(?P<pk>[^/.]+)/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # DELETE/PATCH/PUT
    'api/marketplace/^posts/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # DELETE/PATCH/PUT
    'api/marketplace/^posts/(?P<pk>[^/.]+)/favorite/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/hard_delete/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # DELETE
    'api/marketplace/^posts/(?P<pk>[^/.]+)/images/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # DELETE/POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/mark_sold/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/pause/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/renew/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/restore/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/share/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/soft_delete/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/(?P<pk>[^/.]+)/unpause/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/marketplace/^posts/recalculate_all_scores/$': 'marketplace : offres par contexte vendeur, à migrer en T5',  # POST
    'api/moderation/^reports/$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/^reports/(?P<pk>[^/.]+)/$': 'modération : hors contexte vendeur',  # DELETE/PATCH/PUT
    'api/moderation/^reports/(?P<pk>[^/.]+)/author-response/$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/^reports/(?P<pk>[^/.]+)/claim/$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/^reports/(?P<pk>[^/.]+)/reject/$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/^reports/(?P<pk>[^/.]+)/resolve/$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/^sanctions/$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/^sanctions/(?P<pk>[^/.]+)/$': 'modération : hors contexte vendeur',  # DELETE/PATCH/PUT
    'api/moderation/^sanctions/(?P<pk>[^/.]+)/lift/$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/forbidden-items/^$': 'modération : hors contexte vendeur',  # POST
    'api/moderation/forbidden-items/^(?P<pk>[^/.]+)/$': 'modération : hors contexte vendeur',  # DELETE/PATCH/PUT
}


def _route_string(prefix, pattern):
    return prefix + str(pattern.pattern)


def _walk(resolver, prefix=''):
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            yield from _walk(entry, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), entry.callback


def _view_class(callback):
    return getattr(callback, 'cls', None) or getattr(callback, 'view_class', None)


def _write_methods(callback, view_class):
    actions = getattr(callback, 'actions', None)  # ViewSet : méthode HTTP -> action
    if actions:
        return sorted(m for m in actions if m in WRITE_METHODS)
    return sorted(m for m in WRITE_METHODS if m in view_class.http_method_names and hasattr(view_class, m))


def _has_guard(view_class):
    if issubclass(view_class, services.ActingContextMixin):
        return True
    if getattr(view_class, 'acting_context_exempt', ''):
        return True
    return any(getattr(p, 'acting_context_capability', None) for p in getattr(view_class, 'permission_classes', ()))


def collect_unguarded_write_routes():
    found = {}
    for route, callback in _walk(get_resolver()):
        if '(?P<format>' in route:  # doublon « suffixe de format » d'une route déjà comptée
            continue
        view_class = _view_class(callback)
        if view_class is None or not issubclass(view_class, APIView):
            continue
        methods = _write_methods(callback, view_class)
        if methods and not _has_guard(view_class):
            found[route] = methods
    return found


class WriteRouteGuardTests(SimpleTestCase):
    def test_no_new_unguarded_write_route(self):
        found = collect_unguarded_write_routes()
        new = sorted(set(found) - set(LEGACY_WRITE_ROUTES))
        self.assertEqual(
            new, [],
            "Nouvelle vue d'écriture sans garde de contexte : utiliser ActingContextMixin / capability_permission, "
            "ou déclarer acting_context_exempt = \"raison\".",
        )

    def test_legacy_list_is_up_to_date(self):
        found = collect_unguarded_write_routes()
        stale = sorted(set(LEGACY_WRITE_ROUTES) - set(found))
        self.assertEqual(
            stale, [],
            "Entrée obsolète (vue supprimée, gardée ou exemptée) : retirer de LEGACY_WRITE_ROUTES.",
        )

    def test_guard_detection_works(self):
        class Guarded(services.ActingContextMixin, APIView):
            def post(self, request):
                pass

        class Exempt(APIView):
            acting_context_exempt = "toujours personnel"

            def post(self, request):
                pass

        class ByPermission(APIView):
            permission_classes = [services.capability_permission('offer.publish')]

            def post(self, request):
                pass

        class Bare(APIView):
            def post(self, request):
                pass

        self.assertTrue(all(_has_guard(c) for c in (Guarded, Exempt, ByPermission)))
        self.assertFalse(_has_guard(Bare))
        self.assertEqual(_write_methods(Bare.as_view(), Bare), ['post'])
