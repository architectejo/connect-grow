// Textes de l'interface en français. Pour ajouter le lingala : créer ln.ts avec
// les mêmes clés et l'enregistrer dans i18n/index.ts.
const fr = {
  brand: {
    name: "Connecte+",
    tagline: "Marketplace de confiance",
  },
  nav: {
    home: "Accueil",
    marketplace: "Marketplace",
    explore: "Explorer",
    businesses: "Entreprises",
    publish: "Publier",
    messages: "Messages",
    profile: "Profil",
    dashboard: "Tableau de bord",
    myProfile: "Mon profil",
    favorites: "Favoris",
    settings: "Paramètres",
    trash: "Corbeille",
    login: "Se connecter",
    register: "Créer un compte",
    logout: "Déconnexion",
    openMenu: "Ouvrir le menu",
    closeMenu: "Fermer le menu",
    theme: "Thème",
    mainNavigation: "Navigation principale",
  },
  theme: {
    toggle: "Changer le thème",
    light: "Clair",
    dark: "Sombre",
    system: "Système",
  },
  price: {
    negotiable: "Discutable",
  },
  trust: {
    newSeller: "Nouveau vendeur",
    newSellerShort: "Nouveau",
    newSellerSuffix: "vendeur",
    reviews_one: "{{count}} avis",
    reviews_other: "{{count}} avis",
    ratingLabel: "Note de confiance : {{score}} sur 5",
    memberSince: "Membre depuis {{date}}",
  },
  badge: {
    verified: "Vérifié",
    reliable: "Vendeur fiable",
    trending: "Tendance",
    sponsored: "Sponsorisé",
    exchangeable: "Échangeable",
    service: "Service",
    NEUF: "Neuf",
    OCCASION: "Occasion",
    RECONDITIONNE: "Reconditionné",
  },
  post: {
    views_one: "{{count}} vue",
    views_other: "{{count}} vues",
    addFavorite: "Ajouter aux favoris",
    removeFavorite: "Retirer des favoris",
    noImage: "Pas de photo",
    contact: {
      sendMessage: "Envoyer un message",
      sendMessageShort: "Contacter",
      phoneSoon: "Bientôt disponible : le contact par téléphone se fera avec l'accord du vendeur",
    },
    status: {
      ACTIVE: "En ligne",
      PAUSED: "En pause",
      SOLD: "Vendue",
      EXPIRED: "Expirée",
    },
  },
  errors: {
    generic: "Une erreur est survenue. Réessayez.",
    network: "Connexion impossible. Vérifiez votre réseau puis réessayez.",
    tooManyAttempts_one: "Trop de tentatives, réessayez dans {{count}} seconde.",
    tooManyAttempts_other: "Trop de tentatives, réessayez dans {{count}} secondes.",
    tooManyAttemptsNoDelay: "Trop de tentatives, réessayez dans quelques instants.",
    server: "Le service rencontre un problème. Réessayez dans quelques instants.",
    notFound: "Cette ressource est introuvable.",
    forbidden: "Vous n'avez pas le droit d'effectuer cette action.",
    conflict: "Cette action a déjà été effectuée.",
  },
  common: {
    cancel: "Annuler",
  },
  auth: {
    logoutAllFailed: "Déconnexion locale uniquement : les autres appareils n'ont pas pu être déconnectés.",
    refreshPaused: "Actualisation en pause : trop de requêtes, elle reprendra automatiquement.",
  },
  settings: {
    phonePurpose:
      "Votre numéro reste privé : il sert à vous connecter et à réinitialiser votre mot de passe. Le contact par téléphone se fera avec votre accord.",
    samePhone: "Ce numéro est déjà celui de votre compte.",
    passwordChanged: "Mot de passe modifié. Reconnectez-vous avec le nouveau.",
    logoutAll: "Se déconnecter de tous les appareils",
    logoutAllTitle: "Déconnecter tous les appareils ?",
    logoutAllDescription: "Vous serez déconnecté ici et sur tous vos autres appareils. Vous devrez vous reconnecter partout.",
    logoutAllConfirm: "Tout déconnecter",
  },
  otp: {
    sentBefore: "Si ce numéro peut recevoir un code, un SMS à 6 chiffres lui a été envoyé :",
  },
  kyc: {
    delete: "Supprimer",
    deleteConfirmTitle: "Supprimer ce document ?",
    deleteConfirmDescription: "« {{title}} » sera retiré de votre dossier. Vous pourrez en envoyer un nouveau.",
    deleteLabel: "Supprimer le document : {{title}}",
  },
  businesses: {
    loadMore: "Voir plus d'entreprises",
  },
  states: {
    errorTitle: "Une erreur est survenue",
    errorDescription: "Vérifiez votre connexion internet puis réessayez.",
    retry: "Réessayer",
    emptyTitle: "Rien à afficher pour l'instant",
    offline: "Connexion perdue. Les contenus déjà chargés restent consultables.",
    backOnline: "Connexion rétablie",
    loading: "Chargement…",
  },
};

export default fr;
export type Translations = typeof fr;
