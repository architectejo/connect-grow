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
    notFound: "Cette ressource est introuvable.",
    forbidden: "Vous n'avez pas le droit d'effectuer cette action.",
    conflict: "Cette action a déjà été effectuée.",
  },
  settings: {
    samePhone: "Ce numéro est déjà celui de votre compte.",
    passwordChanged: "Mot de passe modifié. Reconnectez-vous avec le nouveau.",
    logoutAll: "Se déconnecter de tous les appareils",
  },
  otp: {
    sentBefore: "Si ce numéro peut recevoir un code, un SMS à 6 chiffres lui a été envoyé :",
  },
  kyc: {
    delete: "Supprimer",
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
