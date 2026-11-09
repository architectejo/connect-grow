/** Remplaçant de test pour `virtual:pwa-register/react` (module virtuel de vite-plugin-pwa, absent sous Vitest). */
const noop = () => undefined;

export function useRegisterSW() {
  return {
    needRefresh: [false, noop] as const,
    offlineReady: [false, noop] as const,
    updateServiceWorker: async () => undefined,
  };
}
