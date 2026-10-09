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
