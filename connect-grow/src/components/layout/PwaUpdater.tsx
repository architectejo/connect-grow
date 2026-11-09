import { useEffect } from "react";
import { useRegisterSW } from "virtual:pwa-register/react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

const CHECK_INTERVAL = 60 * 60 * 1000;

/**
 * Enregistre le service worker (application installable, contenus consultables hors ligne)
 * et propose de recharger quand une nouvelle version est publiée.
 */
export function PwaUpdater() {
  const { t } = useTranslation();
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
    toast.success(t("pwa.offlineReady"));
    setOfflineReady(false);
  }, [offlineReady, setOfflineReady, t]);

  useEffect(() => {
    if (!needRefresh) return;
    toast(t("pwa.updateAvailable"), {
      duration: Infinity,
      action: { label: t("pwa.update"), onClick: () => updateServiceWorker(true) },
    });
  }, [needRefresh, updateServiceWorker, t]);

  return null;
}
