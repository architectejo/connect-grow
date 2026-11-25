import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Wifi, WifiOff } from "lucide-react";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { cn } from "@/lib/utils";

/** Bandeau de connexion perdue, puis confirmation brève au retour du réseau. */
export function OfflineBanner() {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  const wasOffline = useRef(false);
  const [showBackOnline, setShowBackOnline] = useState(false);

  useEffect(() => {
    if (!online) {
      wasOffline.current = true;
      setShowBackOnline(false);
      return;
    }
    if (wasOffline.current) {
      wasOffline.current = false;
      setShowBackOnline(true);
      const timer = window.setTimeout(() => setShowBackOnline(false), 3000);
      return () => window.clearTimeout(timer);
    }
  }, [online]);

  if (online && !showBackOnline) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "fixed inset-x-0 top-0 z-[60] flex animate-slide-down items-center justify-center gap-2 px-4 py-2 text-center text-xs font-semibold shadow-card sm:text-sm",
        online ? "bg-success text-success-foreground" : "bg-foreground text-background",
      )}
    >
      {online ? <Wifi className="h-4 w-4 shrink-0" aria-hidden /> : <WifiOff className="h-4 w-4 shrink-0" aria-hidden />}
      {online ? t("states.backOnline") : t("states.offline")}
    </div>
  );
}
