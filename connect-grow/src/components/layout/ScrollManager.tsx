import { useEffect } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

/**
 * Remonte en haut de page à chaque navigation, et descend jusqu'à l'ancre (#section) si l'URL en contient une.
 * Le retour arrière (POP) garde la position gérée par le navigateur.
 */
export function ScrollManager() {
  const { pathname, hash } = useLocation();
  const navigationType = useNavigationType();

  useEffect(() => {
    if (hash) {
      // Laisse la page cible se rendre avant de chercher l'ancre
      const timer = window.setTimeout(() => {
        document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView({ behavior: "smooth" });
      }, 50);
      return () => window.clearTimeout(timer);
    }
    if (navigationType !== "POP") window.scrollTo(0, 0);
  }, [pathname, hash, navigationType]);

  return null;
}
