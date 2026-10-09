import { useEffect } from "react";
import { useRegisterSW } from "virtual:pwa-register/react";
import { toast } from "sonner";

const CHECK_INTERVAL = 60 * 60 * 1000;

/**
 * Enregistre le service worker (application installable, contenus consultables hors ligne)
 * et propose de recharger quand une nouvelle version est publiée.
 */
export function PwaUpdater() {
  const {
    needRefresh: [needRefresh],
    offlineReady: [offlineReady, setOfflineReady],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      // Vérifie les mises à jour une fois par heure tant que l'application reste ouverte
      if (registration) window.setInterval(() => registration.update(), CHECK_INTERVAL);
    },
  });

  useEffect(() => {
    if (!offlineReady) return;
    toast.success("Connecte+ est prête à fonctionner hors ligne.");
    setOfflineReady(false);
  }, [offlineReady, setOfflineReady]);

  useEffect(() => {
    if (!needRefresh) return;
    toast("Une nouvelle version est disponible.", {
      duration: Infinity,
      action: { label: "Mettre à jour", onClick: () => updateServiceWorker(true) },
    });
  }, [needRefresh, updateServiceWorker]);

  return null;
}
