import { Component, type ErrorInfo, type ReactNode } from "react";
import i18n from "@/i18n";

const RELOAD_GUARD_KEY = "connecte:chunk-reload";

/** Un fichier de page n'a pas pu être téléchargé (déploiement, redémarrage du serveur de dev, réseau coupé). */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /dynamically imported module|Importing a module script failed|ChunkLoadError|Loading chunk|error loading dynamically/i.test(message);
}

interface Props {
  children: ReactNode;
  /** Quand cette valeur change (ex. nouvelle page), l'erreur est effacée et les enfants sont réaffichés. */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/**
 * Filet de sécurité : une exception d'affichage ne doit jamais laisser un écran blanc.
 * Textes lus dans i18n directement : le composant doit fonctionner même si un fournisseur au-dessus a échoué.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] Erreur d'affichage", error, info.componentStack);
    // Page obsolète après une mise à jour : un seul rechargement automatique, pas de boucle
    if (isChunkLoadError(error)) {
      try {
        if (!sessionStorage.getItem(RELOAD_GUARD_KEY)) {
          sessionStorage.setItem(RELOAD_GUARD_KEY, "1");
          window.location.reload();
        }
      } catch {
        /* stockage indisponible : l'écran de secours reste affiché */
      }
    }
  }

  componentDidUpdate(previous: Props) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const t = i18n.t.bind(i18n);
    return (
      <div role="alert" className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
        <h1 className="text-xl font-extrabold">{t("crash.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("crash.description")}</p>
        <div className="flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            {t("crash.reload")}
          </button>
          <a href="/" className="rounded-lg border px-4 py-2 text-sm font-semibold">
            {t("crash.home")}
          </a>
        </div>
        <details className="w-full text-left text-xs text-muted-foreground">
          <summary className="cursor-pointer">{t("crash.details")}</summary>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-2">{`${error.name}: ${error.message}`}</pre>
        </details>
      </div>
    );
  }
}
