import hashlib
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from rest_framework import generics, permissions, serializers, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.common.contexts import CONTEXT_ORGANIZATION
from apps.common.exception_handler import CodedAPIException
from apps.moderation.services import record_audit

from .identifiers import normalize_identifier
from .kyc_files import EXTENSION_TO_CONTENT_TYPE
from .models import KycDocument, OtpCode, User, phone_validator
from .permissions import CanReviewKyc
from .serializers import (
    IdentifierTokenObtainPairSerializer, KycDocumentSerializer, OrganizationKycDocumentSerializer,
    UserSerializer,
)
from .services import (
    ActingContextMixin, ContactSettingsError, get_acting_context, KycError, decide_kyc_document, get_contact_settings,
    get_contexts_for_user, get_unavailable_organizations,
    get_document_for_download,
    revoke_all_sessions, set_channel_consent, set_contact_phone, validate_new_password, verify_contact_phone,
)
from .sms import send_otp_sms
from .throttles import (
    ContactSettingsThrottle, ProfileWriteIpThrottle, ProfileWriteThrottle, RegisterIpThrottle,
    ChangePasswordThrottle, ContextsListThrottle, FailureLimiter, LoginIpThrottle,
    OtpConfirmIpThrottle,
    LogoutIpThrottle, OtpRequestIpThrottle, OtpRequestPhoneDailyThrottle, OtpRequestPhoneThrottle, RefreshIpThrottle,
)

logger = logging.getLogger(__name__)

# Capacité exigée pour les réglages de contact : contexte personnel ou prestataire (toujours), organisation
# (propriétaire ou administrateur seulement), ADR 0006, section 5.
CONTACT_CAPABILITY = 'contact.manage_channels'

# Échecs de connexion / de confirmation de reset : délai croissant par couple identifiant+IP.
LOGIN_FAILURES = FailureLimiter('login')
RESET_FAILURES = FailureLimiter('reset')


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]


def failure_key(request, identifier):
    """Clé du couple (identifiant normalisé, IP), ou None sans identifiant exploitable.
    L'identifiant est normalisé (casse, séparateurs, indicatif) pour qu'on ne contourne pas
    le plafond en variant l'écriture."""
    if not isinstance(identifier, str) or not identifier.strip():
        return None
    ip = LoginIpThrottle().get_ident(request)
    return _digest(f"{normalize_identifier(identifier)}|{ip}")


def as_text(value):
    """Texte propre pour un champ attendu en chaîne ; None si le type est inexploitable
    (liste, objet, booléen, vide) : la requête est alors refusée sans compter d'échec."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class LoginView(TokenObtainPairView):
    """Connexion par e-mail ou par téléphone (CDC 3.1). Limites : IP (toutes requêtes) et
    échecs par couple identifiant+IP puis par identifiant (réinitialisés au succès)."""

    serializer_class = IdentifierTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginIpThrottle]

    def post(self, request, *args, **kwargs):
        data = request.data if hasattr(request.data, 'get') else {}
        keys = failure_key(request, data.get('email') or data.get('phone'))
        if keys:
            LOGIN_FAILURES.check(keys)
        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            if keys:
                LOGIN_FAILURES.failure(keys)
            raise
        if keys and response.status_code == status.HTTP_200_OK:
            LOGIN_FAILURES.success(keys)
        return response


class RefreshView(TokenRefreshView):
    """Renouvellement du jeton d'accès : scope de limitation distinct (`refresh`)."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [RefreshIpThrottle]


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny] # Tout le monde peut s'inscrire
    serializer_class = UserSerializer
    throttle_classes = [RegisterIpThrottle]

class UserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    throttle_classes = [ProfileWriteThrottle, ProfileWriteIpThrottle]
    permission_classes = [permissions.IsAuthenticated] # Nécessite d'être connecté

    def get_object(self):
        return self.request.user


class ContextListView(APIView):
    """GET : contextes que le compte peut activer (ADR 0006, 9.1). Liste bornée, non paginée, servie dans
    l'enveloppe des autres listes. Ignore `X-Context` : elle décrit tous les contextes. `capabilities` sert
    à masquer des boutons ; l'autorisation reste côté serveur. Jamais mise en cache (rôles sensibles)."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ContextsListThrottle]

    def get(self, request):
        def serialize(item):
            return {
                'type': item.type, 'id': str(item.id), 'name': item.name, 'role': item.role,
                'org_type': item.org_type,
                'photo': request.build_absolute_uri(item.photo) if item.photo else None,
                'capabilities': list(item.capabilities),
                'migrated_from_business': item.migrated_from_business,
                'status': item.status,
            }

        results = [serialize(item) for item in get_contexts_for_user(request.user)]
        unavailable = [serialize(item) for item in get_unavailable_organizations(request.user)]
        response = Response({
            'count': len(results), 'next': None, 'previous': None, 'results': results, 'unavailable': unavailable,
        })
        response['Cache-Control'] = 'private, no-store'
        return response


def password_error(exc):
    """Réponse 400 uniforme pour un mot de passe refusé (clé `error` comme ailleurs)."""
    messages = [str(m) for m in exc.detail]
    return Response({'error': messages[0], 'errors': messages}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ChangePasswordThrottle]

    def post(self, request):
        user = request.user
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        # Vérification de l'ancien mot de passe
        if not user.check_password(old_password):
            return Response(
                {"error": "L'ancien mot de passe est incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_new_password(new_password, user)
        except serializers.ValidationError as exc:
            return password_error(exc)

        # Mise à jour du mot de passe
        user.set_password(new_password)
        user.save()
        # Les sessions ouvertes (autres appareils, jeton volé) ne survivent pas au changement.
        revoke_all_sessions(user)
        return Response({"message": "Mot de passe mis à jour avec succès."}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Déconnexion : le refresh token fourni est mis sur liste noire.

    Public (ni authentification ni jeton d'accès) : le refresh dans le corps prouve la
    possession de la session, et l'access token a souvent expiré à la déconnexion. Réponse
    200 uniforme que le jeton soit valide, forgé, expiré ou déjà révoqué (pas d'oracle) ;
    400 seulement si le champ est absent. Limité par IP (scope `logout`)."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LogoutIpThrottle]

    def post(self, request):
        data = request.data if hasattr(request.data, 'get') else {}
        raw = data.get('refresh')
        if not isinstance(raw, str) or not raw.strip():
            return Response({'error': "Le jeton de rafraîchissement est requis."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(raw).blacklist()
        except TokenError:
            pass
        return Response({'message': "Déconnecté."}, status=status.HTTP_200_OK)


class LogoutAllView(APIView):
    """Déconnexion de tous les appareils : tous les refresh tokens sont révoqués."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        revoked = revoke_all_sessions(request.user)
        return Response({'message': "Toutes les sessions ont été fermées.", 'revoked': revoked})

class OtpRequestView(APIView):
    """CDC 3.1 : envoi d'un code OTP par SMS pour l'inscription, la connexion
    ou la réinitialisation du mot de passe.

    La réponse est identique que le numéro corresponde ou non à un compte (pas
    d'énumération de comptes) : le code n'est émis que si la demande est cohérente."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [OtpRequestIpThrottle, OtpRequestPhoneThrottle, OtpRequestPhoneDailyThrottle]

    def post(self, request):
        phone = request.data.get('phone', '')
        purpose = request.data.get('purpose', OtpCode.PURPOSE_REGISTER)

        # CONTACT_VERIFY n'est émis que par les réglages de contact (utilisateur connecté, ADR 0005).
        if purpose not in dict(OtpCode.PURPOSE_CHOICES) or purpose == OtpCode.PURPOSE_CONTACT_VERIFY:
            return Response({'error': "purpose invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if not isinstance(phone, str):
                raise DjangoValidationError("Numéro invalide.")
            phone_validator(phone)
        except DjangoValidationError:
            return Response(
                {'error': "Numéro invalide. Format attendu : +243XXXXXXXXX."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_exists = User.objects.filter(phone=phone).exists()
        eligible = (purpose == OtpCode.PURPOSE_REGISTER) != user_exists
        if eligible:
            _, code = OtpCode.issue(phone, purpose)
            try:
                send_otp_sms(phone, code, purpose)
            except Exception:  # passerelle SMS absente ou en panne : jamais de 500 ni de différence visible
                logger.exception("Échec d'envoi du SMS OTP (objet %s).", purpose)

        return Response(
            {
                'message': "Si le numéro est éligible, un code a été envoyé par SMS.",
                'expires_in_minutes': OtpCode.VALIDITY_MINUTES,
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """CDC 3.1 : réinitialisation du mot de passe par OTP."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [OtpConfirmIpThrottle]

    def post(self, request):
        data = request.data if hasattr(request.data, 'get') else {}
        phone = as_text(data.get('phone'))
        code = as_text(data.get('code'))
        new_password = data.get('new_password')

        if not (phone and code and new_password):
            return Response(
                {'error': "phone, code et new_password sont requis."}, status=status.HTTP_400_BAD_REQUEST
            )

        keys = failure_key(request, phone)
        RESET_FAILURES.check(keys)

        # Contrôle générique du mot de passe AVANT de consommer le code : identique que le
        # compte existe ou non (aucun oracle d'existence), et un mot de passe trivial ne brûle
        # pas l'OTP.
        try:
            validate_new_password(new_password)
        except serializers.ValidationError as exc:
            return password_error(exc)

        user = User.objects.filter(phone=phone).first()
        otp = (
            OtpCode.objects.filter(phone=phone, purpose=OtpCode.PURPOSE_PASSWORD_RESET, is_used=False)
            .order_by('-created_at')
            .first()
        )
        if not otp or not otp.verify(code) or not user:
            RESET_FAILURES.failure(keys)
            return Response({'error': "Code invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

        # Code valide : seul le titulaire arrive ici ; la similarité avec ses données
        # (e-mail, nom...) peut maintenant être contrôlée sans rien révéler à un tiers.
        try:
            validate_new_password(new_password, user)
        except serializers.ValidationError as exc:
            return password_error(exc)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        revoke_all_sessions(user)
        RESET_FAILURES.success(keys)
        return Response({'message': "Mot de passe mis à jour avec succès."}, status=status.HTTP_200_OK)


class KycReviewQueueView(generics.ListAPIView):
    """File de vérification Business pour la modération (CDC 3.11)."""

    serializer_class = KycDocumentSerializer
    permission_classes = [CanReviewKyc]
    queryset = KycDocument.objects.filter(status=KycDocument.STATUS_EN_ATTENTE).select_related(
        'organization',
    )


class KycDecisionView(APIView):
    """Validation ou refus motivé d'une pièce KYC par la modération (CDC 3.11).

    Une pièce en attente reçoit une seule décision. Une pièce validée peut être
    révoquée (REFUSE avec motif) ; une pièce refusée est définitive (le titulaire
    redépose). Un examinateur ne décide jamais sur sa propre pièce."""

    permission_classes = [CanReviewKyc]

    def post(self, request, pk):
        reason = request.data.get('reason', '')
        if not isinstance(reason, str):
            return Response({'error': "reason doit être un texte."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            doc = decide_kyc_document(pk, request.user, request.data.get('decision'), reason.strip())
        except KycError as exc:
            return Response({'error': exc.message}, status=exc.status_code)
        return Response(KycDocumentSerializer(doc, context={'request': request}).data, status=status.HTTP_200_OK)


class KycDocumentDownloadView(APIView):
    """Accès aux pièces KYC réservé aux examinateurs habilités (CDC 4.2, 5.8), journalisé."""

    permission_classes = [CanReviewKyc]

    def get(self, request, pk):
        try:
            doc = get_document_for_download(pk, request.user)
        except KycError as exc:
            return Response({'error': exc.message}, status=exc.status_code)
        try:
            handle = doc.file.open('rb')
        except (ValueError, OSError):
            return Response({'error': "Fichier introuvable."}, status=status.HTTP_404_NOT_FOUND)
        record_audit(
            request.user, 'KYC_DOWNLOADED', target=doc,
            details=f"Pièce {doc.get_document_type_display()} consultée.",
            context=(CONTEXT_ORGANIZATION, doc.organization_id),
        )
        extension = doc.file.name.rsplit('.', 1)[-1].lower() if '.' in doc.file.name else 'bin'
        response = FileResponse(
            handle, as_attachment=True, filename=f"piece-kyc-{doc.pk}.{extension}",
            content_type=EXTENSION_TO_CONTENT_TYPE.get(extension, 'application/octet-stream'),
        )
        response['Cache-Control'] = 'private, no-store'  # pièce d'identité : jamais en cache
        return response


class _ContactSettingsBase(ActingContextMixin, APIView):
    """Réglages de contact du contexte actif (ADR 0005, 5.1 ; ADR 0006, 9.8). L'en-tête `X-Context` désigne le
    contexte : compte (personnel ou prestataire) ou organisation (capacité `contact.manage_channels`, propriétaire
    ou administrateur). Aucun identifiant dans l'URL. Numéros masqués ; jamais mis en cache."""

    permission_classes = [permissions.IsAuthenticated]

    allow_restricted = False  # vrai pour un retrait de consentement (ADR 0005, C4)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Contexte résolu et capacité contrôlée avant toute lecture ou écriture (refus : 403 `DENY_*`).
        if self.allow_restricted:
            get_acting_context(request, allow_restricted=True)  # mémorisé : `acting_context` le réutilise
        self.authorize_capability(CONTACT_CAPABILITY)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        return response

    def current(self, request):
        return Response(get_contact_settings(request.user, self.acting_context))

    @staticmethod
    def body(request):
        return request.data if hasattr(request.data, 'get') else {}

    def run(self, action, *args, **kwargs):
        try:
            return action(*args, context=self.acting_context, **kwargs)
        except ContactSettingsError as exc:
            if exc.code == 'channel_not_available':
                # Contrat ADR 0006, 17.1 (Q-F3) : erreur de champ `channel` + code machine.
                raise ChannelNotAvailable(exc.message)
            raise CodedAPIException(exc.message, exc.code, status_code=exc.status_code)


class ChannelNotAvailable(serializers.ValidationError):
    """400 `{"channel": ["..."], "code": "channel_not_available"}` : le canal demandé n'est pas proposable."""

    def __init__(self, message):
        super().__init__({'channel': [message]})
        self.detail['detail'] = message
        self.detail['code'] = 'channel_not_available'


class ContactSettingsView(_ContactSettingsBase):
    def get(self, request):
        return self.current(request)


class ContactPhoneView(_ContactSettingsBase):
    """PUT : définit le numéro de contact (saisi, ou numéro de connexion sur geste explicite, jamais pour une
    organisation) et envoie un code SMS s'il n'est pas vérifié d'emblée. Limites des OTP + réglages."""

    throttle_classes = [
        ContactSettingsThrottle, OtpRequestIpThrottle, OtpRequestPhoneThrottle, OtpRequestPhoneDailyThrottle,
    ]

    def put(self, request):
        data = self.body(request)
        use_login = data.get('use_login_phone', False)
        phone = data.get('phone')
        if not isinstance(use_login, bool) or (phone is not None and not isinstance(phone, str)):
            raise CodedAPIException("Numéro invalide. Format attendu : +243XXXXXXXXX.", 'phone_invalid')
        self.run(set_contact_phone, request.user, phone=phone, use_login_phone=use_login)
        return self.current(request)


class ContactPhoneVerifyView(_ContactSettingsBase):
    throttle_classes = [ContactSettingsThrottle, OtpConfirmIpThrottle]

    def post(self, request):
        self.run(verify_contact_phone, request.user, self.body(request).get('code'))
        return self.current(request)


class ContactChannelView(_ContactSettingsBase):
    throttle_classes = [ContactSettingsThrottle]

    @property
    def allow_restricted(self):
        """Retirer un canal reste permis même à un compte sanctionné (comme `org.leave`) ; l'activer ne l'est pas."""
        data = getattr(self.request, 'data', None)
        return hasattr(data, 'get') and data.get('enabled') is False

    def put(self, request, channel):
        data = self.body(request)
        enabled = data.get('enabled')
        text_version = data.get('text_version')
        if channel not in ('MESSAGE', 'CALL', 'WHATSAPP'):
            raise CodedAPIException("Canal inconnu.", 'channel_unknown', status_code=404)
        if not isinstance(enabled, bool):
            raise serializers.ValidationError({'enabled': ["Un booléen est attendu."]})
        if text_version is not None and not isinstance(text_version, str):
            raise serializers.ValidationError({'text_version': ["Un texte est attendu."]})
        self.run(set_channel_consent, request.user, channel, enabled=enabled, text_version=text_version)
        return self.current(request)
