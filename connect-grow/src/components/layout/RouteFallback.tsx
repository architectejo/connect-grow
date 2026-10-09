import { useEffect, useState } from "react";

/**
 * Affiché pendant le téléchargement d'une page. Invisible les 200 premières millisecondes
 * pour ne pas faire clignoter l'écran sur une bonne connexion.
 */
export function RouteFallback() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 200);
    return () => window.clearTimeout(timer);
  }, []);

  if (!visible) return null;

  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 top-0 z-[60]">
      <span className="sr-only">Chargement de la page…</span>
      <div className="h-1 overflow-hidden bg-primary/15">
        <div className="h-full w-1/3 animate-route-progress rounded-full bg-primary" />
      </div>
    </div>
  );
}
