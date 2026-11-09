import { useId } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2 } from "lucide-react";
import { RoleBadge, SellerTypeBadge, UserAvatar } from "@/components/common";
import { OrganizationStatusBadge } from "@/components/organizations/OrganizationStatusBadge";
import { Button } from "@/components/ui/button";
import { useUnavailableOrganizations } from "@/contexts/ActiveContextContext";

/**
 * « Organisations indisponibles » de Mes profils : absente quand la liste est vide. Aucune carte ne peut devenir
 * le profil actif (pas de « Agir sous ce profil ») ; le seul lien mène à la vue d'état.
 */
export function UnavailableOrganizationsSection() {
  const { t } = useTranslation();
  const unavailable = useUnavailableOrganizations();
  const titleId = useId();
  if (unavailable.length === 0) return null;

  return (
    <section aria-labelledby={titleId} className="space-y-3">
      <div>
        <h2 id={titleId} className="flex items-center gap-2 font-display text-lg font-bold">
          <Building2 className="h-5 w-5 text-muted-foreground" aria-hidden /> {t("org.unavailable.listTitle")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("org.unavailable.listDescription")}</p>
      </div>
      <ul className="grid gap-3">
        {unavailable.map((org) => (
          <li key={org.id}>
            <article className="relative flex flex-col gap-3 rounded-2xl border bg-card p-4 shadow-soft focus-within:ring-2 focus-within:ring-ring sm:flex-row sm:items-center">
              <UserAvatar src={org.photo} name={org.name} size="md" shape="square" />
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-semibold" title={org.name}>
                  {org.name}
                </h3>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  <SellerTypeBadge contextType="ORGANIZATION" orgType={org.org_type} />
                  <RoleBadge role={org.role} />
                  <OrganizationStatusBadge status={org.status} />
                </div>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link to={`/organizations/${org.id}`} aria-label={t("org.unavailable.seeAria", { name: org.name })} className="after:absolute after:inset-0 after:content-['']">
                  {t("org.unavailable.see")}
                </Link>
              </Button>
            </article>
          </li>
        ))}
      </ul>
    </section>
  );
}
