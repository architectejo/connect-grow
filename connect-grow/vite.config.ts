import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import { VitePWA } from "vite-plugin-pwa";
import { isCacheableApiContent } from "./src/lib/cache-rules";

// Bibliothèques regroupées en fichiers stables : une mise à jour de l'application
// ne force pas les utilisateurs à les retélécharger (forfaits de données limités, CDC 2.2).
// Un nom finissant par « / » ou « - » est un préfixe (toute une famille de paquets).
// Recharts n'est volontairement pas regroupé ici : un groupe manuel aspire aussi ses petites
// dépendances partagées (clsx…), ce qui le ferait télécharger dès l'accueil.
const VENDOR_CHUNKS: Record<string, string[]> = {
  react: ["react", "react-dom", "react-router", "react-router-dom", "scheduler", "@remix-run/"],
  radix: ["@radix-ui/", "@floating-ui/"],
  query: ["@tanstack/"],
  forms: ["react-hook-form", "@hookform/", "zod"],
};

/** Nom du paquet npm d'un module (« @radix-ui/react-dialog », « recharts »…), ou null hors node_modules. */
function packageOf(id: string): string | null {
  const normalized = id.replace(/\\/g, "/"); // chemins Windows
  const index = normalized.lastIndexOf("/node_modules/");
  if (index === -1) return null;
  const [first, second] = normalized.slice(index + "/node_modules/".length).split("/");
  return first.startsWith("@") ? `${first}/${second}` : first;
}

const ONE_DAY = 24 * 60 * 60;

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
  },
  plugins: [
    react(),
    mode === "development" && componentTagger(),
    // Application installable et utilisable hors ligne (CDC 1.4, 4.4, 6.3)
    VitePWA({
      registerType: "prompt",
      includeAssets: ["favicon.ico", "apple-touch-icon.png", "logo-mark.png"],
      manifest: {
        name: "Connecte+ — Marketplace de confiance",
        short_name: "Connecte+",
        description: "Achetez, vendez et échangez près de chez vous à Kinshasa, auprès de vendeurs dont la réputation se vérifie.",
        lang: "fr",
        dir: "ltr",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "portrait",
        theme_color: "#184dbf",
        background_color: "#fcfaf8",
        categories: ["shopping", "business", "lifestyle"],
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
        shortcuts: [
          { name: "Publier une annonce", short_name: "Publier", url: "/create-post", icons: [{ src: "pwa-192x192.png", sizes: "192x192" }] },
          { name: "Mes favoris", short_name: "Favoris", url: "/favorites", icons: [{ src: "pwa-192x192.png", sizes: "192x192" }] },
        ],
      },
      workbox: {
        // Préchargement limité à la coquille de l'application et aux pages les plus visitées :
        // les autres pages sont mises en cache à leur première ouverture (forfaits limités, CDC 2.2).
        globPatterns: [
          "index.html",
          "assets/index-*.{js,css}",
          "assets/{react,radix,query,workbox-window}*.js",
          "assets/{Marketplace,PostDetail,format}-*.js",
          "assets/*-latin-wght-normal-*.woff2",
          "{favicon.ico,logo-mark.png,pwa-192x192.png}",
        ],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/media\//, /^\/admin\//],
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            // Autres pages et polices : noms de fichiers versionnés, donc réutilisables sans revalidation
            urlPattern: ({ url, sameOrigin }) => sameOrigin && url.pathname.startsWith("/assets/"),
            handler: "CacheFirst",
            options: { cacheName: "app-assets", expiration: { maxEntries: 80, maxAgeSeconds: 60 * ONE_DAY } },
          },
          {
            // Référentiels : changent rarement
            urlPattern: ({ url }) => /\/api\/(v1\/)?marketplace\/(categories|cities|communes)\//.test(url.pathname),
            handler: "StaleWhileRevalidate",
            options: { cacheName: "api-referentiels", expiration: { maxEntries: 20, maxAgeSeconds: 7 * ONE_DAY } },
          },
          {
            // Contenus publics : le réseau d'abord, le cache si la connexion tombe (contenus déjà vus consultables)
            urlPattern: isCacheableApiContent,
            handler: "NetworkFirst",
            options: {
              cacheName: "api-annonces",
              networkTimeoutSeconds: 6,
              expiration: { maxEntries: 150, maxAgeSeconds: 2 * ONE_DAY },
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            // Photos des annonces et avatars
            urlPattern: ({ url, request }) => request.destination === "image" && url.pathname.includes("/media/"),
            handler: "CacheFirst",
            options: {
              cacheName: "photos",
              expiration: { maxEntries: 250, maxAgeSeconds: 30 * ONE_DAY, purgeOnQuotaError: true },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const packageName = packageOf(id);
          if (!packageName) return undefined;
          for (const [chunk, packages] of Object.entries(VENDOR_CHUNKS)) {
            const matches = (pkg: string) => (/[/-]$/.test(pkg) ? packageName.startsWith(pkg) : packageName === pkg);
            if (packages.some(matches)) return chunk;
          }
          return undefined;
        },
      },
    },
  },
}));
