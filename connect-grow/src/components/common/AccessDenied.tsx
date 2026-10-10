import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";
import { EmptyState } from "./StateViews";

interface AccessDeniedProps {
  title?: string;
  description: ReactNode;
  /** Sortie proposée : « Mes profils », « Retour »… */
  action?: ReactNode;
  className?: string;
}

/** Permission refusée (403) : l'accès n'est pas possible avec ce profil ou ce rôle. Réutilise EmptyState. */
export function AccessDenied({ title, description, action, className }: AccessDeniedProps) {
  const { t } = useTranslation();
  return <EmptyState icon={Lock} title={title ?? t("states.accessDeniedTitle")} description={description} action={action} className={className} />;
}
