import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useIsMobile } from "@/hooks/use-mobile";
import { capabilityLabelKey, groupCapabilities } from "@/lib/role-access";

/** Au-delà de ce nombre d'accès, la liste est repliée sur mobile (spec D2 §9.2). */
const MOBILE_OPEN_MAX = 6;

/**
 * Accès d'un rôle proposé, traduits et regroupés par thème (spec D2 §9.2). Un code inconnu n'est jamais masqué : il est compté
 * dans « et N autre(s) accès ». Sur mobile, repliée au-delà de 6 accès ; toujours ouverte sur ordinateur.
 */
export function RoleAccessList({ capabilities, headingLevel = 3 }: { capabilities: readonly string[]; headingLevel?: 3 | 4 }) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const total = new Set(capabilities).size;
  const [open, setOpen] = useState(total <= MOBILE_OPEN_MAX);
  const { groups, others } = groupCapabilities(capabilities);
  const Heading = headingLevel === 3 ? "h3" : "h4";

  const list = (
    <div className="space-y-3">
      {groups.map(({ group, codes }) => (
        <div key={group}>
          <Heading className="text-sm font-semibold">{t(`access.group.${group}`)}</Heading>
          <ul className="mt-1 space-y-1">
            {codes.map((code) => (
              <li key={code} className="flex items-start gap-2 text-sm">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                <span>{t(capabilityLabelKey(code))}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {others > 0 && <p className="text-sm text-muted-foreground">{t("access.others", { count: others })}</p>}
    </div>
  );

  if (!isMobile) return list;
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex min-h-11 w-full items-center justify-between text-left text-sm font-semibold text-primary">
        {t("invitation.preview.accessToggle", { count: total })}
        <ChevronDown className={open ? "h-4 w-4 rotate-180 transition-transform" : "h-4 w-4 transition-transform"} aria-hidden />
      </CollapsibleTrigger>
      <CollapsibleContent>{list}</CollapsibleContent>
    </Collapsible>
  );
}
