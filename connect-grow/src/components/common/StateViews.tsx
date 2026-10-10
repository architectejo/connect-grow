import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Inbox, RefreshCw, WifiOff, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// États d'interface du cahier des charges 6.3 : jamais d'écran blanc.

interface EmptyStateProps {
  icon?: LucideIcon;
  title?: string;
  description?: ReactNode;
  /** Action proposée : publier, élargir la recherche… */
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon: Icon = Inbox, title, description, action, className }: EmptyStateProps) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-dashed bg-card/50 px-6 py-14 text-center",
        className,
      )}
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Icon className="h-7 w-7" aria-hidden />
      </div>
      <h3 className="text-lg font-bold text-foreground">{title ?? t("states.emptyTitle")}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  description?: ReactNode;
  onRetry?: () => void;
  isRetrying?: boolean;
  className?: string;
}

export function ErrorState({ title, description, onRetry, isRetrying, className }: ErrorStateProps) {
  const { t } = useTranslation();
  const offline = typeof navigator !== "undefined" && !navigator.onLine;
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center justify-center rounded-2xl border bg-card px-6 py-14 text-center", className)}
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
        {offline ? <WifiOff className="h-7 w-7" aria-hidden /> : <RefreshCw className="h-7 w-7" aria-hidden />}
      </div>
      <h3 className="text-lg font-bold text-foreground">{title ?? t("states.errorTitle")}</h3>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{description ?? t("states.errorDescription")}</p>
      {onRetry && (
        <Button onClick={onRetry} disabled={isRetrying} variant="outline" className="mt-6">
          <RefreshCw className={cn(isRetrying && "animate-spin")} aria-hidden />
          {t("states.retry")}
        </Button>
      )}
    </div>
  );
}
