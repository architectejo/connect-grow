import { lazy, Suspense, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import Index from "./pages/Index.tsx";
import { ThemeProvider } from "./components/theme-provider";
import { AuthProvider } from "./contexts/AuthContext";
import { BottomNav } from "./components/layout/BottomNav";
import { OfflineBanner } from "./components/common/OfflineBanner";
import { PwaUpdater } from "./components/layout/PwaUpdater";
import { RouteFallback } from "./components/layout/RouteFallback";
import { ScrollManager } from "./components/layout/ScrollManager";
import { shouldRetryQuery } from "./lib/errors";

// Chaque page est un fichier JavaScript séparé, téléchargé à la première visite (réseau 3G, CDC 4.1).
// Seule l'accueil, première page vue, reste dans le paquet initial.
const loadMarketplace = () => import("./pages/Marketplace.tsx");
const loadPostDetail = () => import("./pages/PostDetail.tsx");

const Marketplace = lazy(loadMarketplace);
const PostDetail = lazy(loadPostDetail);
const Login = lazy(() => import("./pages/Login.tsx"));
const Register = lazy(() => import("./pages/Register.tsx"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword.tsx"));
const Dashboard = lazy(() => import("./pages/Dashboard.tsx"));
const PostEditor = lazy(() => import("./pages/PostEditor.tsx"));
const Trash = lazy(() => import("./pages/Trash.tsx"));
const Favorites = lazy(() => import("./pages/Favorites.tsx"));
const Notifications = lazy(() => import("./pages/Notifications.tsx"));
const Settings = lazy(() => import("./pages/Settings.tsx"));
const Verification = lazy(() => import("./pages/Verification.tsx"));
const Messages = lazy(() => import("./pages/Messages.tsx"));
const Businesses = lazy(() => import("./pages/Businesses.tsx"));
const SellerProfile = lazy(() => import("./pages/SellerProfile.tsx"));
const NotFound = lazy(() => import("./pages/NotFound.tsx"));
// Galerie des composants, disponible uniquement en développement
const DesignSystem = import.meta.env.DEV ? lazy(() => import("./pages/DesignSystem.tsx")) : null;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Réseau 3G instable : peu de nouvelles tentatives, pas de rechargement au retour sur l'onglet
      // 4xx (dont 429) : jamais relancé automatiquement ; une seule nouvelle tentative sinon
      retry: shouldRetryQuery,
      staleTime: 30 * 1000,
      refetchOnWindowFocus: false,
    },
  },
});

/** Précharge les pages les plus visitées quand le navigateur n'a rien d'autre à faire. */
function usePrefetchLikelyRoutes() {
  useEffect(() => {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    if (connection?.saveData) return; // L'utilisateur a demandé à économiser ses données
    const prefetch = () => {
      loadMarketplace();
      loadPostDetail();
    };
    // Seulement une fois la page chargée : ne pas concurrencer le premier affichage sur une 3G
    let idleId: number | undefined;
    let timer: number | undefined;
    const schedule = () => {
      if (typeof window.requestIdleCallback === "function") idleId = window.requestIdleCallback(prefetch, { timeout: 10000 });
      else timer = window.setTimeout(prefetch, 3000);
    };
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });
    return () => {
      window.removeEventListener("load", schedule);
      if (idleId !== undefined) window.cancelIdleCallback(idleId);
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);
}

const App = () => {
  usePrefetchLikelyRoutes();

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ThemeProvider defaultTheme="light" storageKey="vite-ui-theme">
          <TooltipProvider>
            <Toaster />
            <PwaUpdater />
            <OfflineBanner />
            {/* startTransition : la page actuelle reste affichée pendant le téléchargement de la suivante */}
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
              <a
                href="#contenu"
                className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
              >
                Aller au contenu
              </a>
              <ScrollManager />
              <Suspense fallback={<RouteFallback />}>
                <Routes>
                  <Route path="/" element={<Index />} />
                  <Route path="/login" element={<Login />} />
                  <Route path="/register" element={<Register />} />
                  <Route path="/forgot-password" element={<ForgotPassword />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/marketplace" element={<Marketplace />} />
                  <Route path="/businesses" element={<Businesses />} />
                  <Route path="/post/:id" element={<PostDetail />} />
                  <Route path="/u/:id" element={<SellerProfile />} />
                  <Route path="/create-post" element={<PostEditor />} />
                  <Route path="/edit-post/:id" element={<PostEditor />} />
                  <Route path="/trash" element={<Trash />} />
                  <Route path="/favorites" element={<Favorites />} />
                  <Route path="/notifications" element={<Notifications />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="/verification" element={<Verification />} />
                  <Route path="/profile" element={<Navigate to="/settings" replace />} />
                  <Route path="/messages" element={<Messages />} />
                  {DesignSystem && <Route path="/design" element={<DesignSystem />} />}
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
              <BottomNav />
            </BrowserRouter>
          </TooltipProvider>
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
};

export default App;
