import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Briefcase, Building2, Check, ChevronsUpDown, UserRound, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle, DrawerTrigger } from "@/components/ui/drawer";
import { Skeleton } from "@/components/ui/skeleton";
import { UserAvatar } from "@/components/common/UserAvatar";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { useOnlineStatus } from "@/hooks/use-online-status";
import type { ContextType, OrganizationRole, OrganizationType } from "@/api/types";
import { cn } from "@/lib/utils";

interface Choice {
  type: ContextType;
  id: string;
  name: string;
  role: OrganizationRole | null;
  orgType: OrganizationType | null;
  photo: string | null;
}

const ICONS: Record<ContextType, LucideIcon> = { USER: UserRound, PROVIDER: Briefcase, ORGANIZATION: Building2 };

/** Libellé du type de profil : « Personnel », « Prestataire », ou le type de l'organisation (« Boutique »…). */
export function contextTypeLabel(t: TFunction, choice: Pick<Choice, "type" | "orgType">): string {
  if (choice.type === "ORGANIZATION" && choice.orgType) return t(`orgType.${choice.orgType}`);
  return t(`context.type.${choice.type}`);
}

const choiceValue = (c: Pick<Choice, "type" | "id">) => `${c.type}:${c.id}`;

function ChoiceRow({ choice }: { choice: Choice }) {
  const { t } = useTranslation();
  const Icon = ICONS[choice.type];
  return (
    <span className="flex min-w-0 flex-1 items-center gap-3">
      <UserAvatar src={choice.photo} name={choice.name} size="sm" shape={choice.type === "ORGANIZATION" ? "square" : "circle"} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-foreground" title={choice.name}>
          {choice.name}
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Icon className="h-3 w-3 shrink-0" aria-hidden />
          <span className="truncate">{contextTypeLabel(t, choice)}</span>
          {choice.role && <span className="shrink-0">· {t(`role.${choice.role}`)}</span>}
        </span>
      </span>
    </span>
  );
}

interface SwitcherProps {
  /** `pill` : pastille de la barre (desktop, menu déroulant). `banner` : bandeau pleine largeur (mobile, feuille basse). */
  variant?: "pill" | "banner";
  /** Liens « Mes profils » et « Créer une organisation » : à activer quand ces écrans existent (F2). */
  showManagementLinks?: boolean;
  className?: string;
}

function useChoices() {
  const ctx = useActiveContext();
  const choices: Choice[] = ctx.contexts.map((c) => ({ type: c.type, id: c.id, name: c.name, role: c.role, orgType: c.org_type, photo: c.photo }));
  const { active } = ctx;
  // Liste pas encore reçue : le profil actif (mémorisé) reste affiché et sélectionné
  if (!choices.some((c) => c.type === active.type && c.id === active.id) && active.id) {
    choices.unshift({ type: active.type, id: active.id, name: active.name, role: active.role, orgType: active.orgType, photo: active.photo });
  }
  return { ...ctx, choices };
}

function LoadError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="space-y-2 p-3 text-sm">
      <p className="text-muted-foreground">{t("context.loadError")}</p>
      <Button type="button" variant="outline" size="sm" onClick={onRetry}>
        {t("states.retry")}
      </Button>
    </div>
  );
}

function ManagementLinks({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  return (
    <div className="flex flex-col gap-1 p-1 text-sm">
      <Link to="/profiles" onClick={onNavigate} className="rounded-md px-2 py-2 font-semibold hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {t("context.myProfiles")}
      </Link>
      {online ? (
        <Link to="/organizations/new" onClick={onNavigate} className="rounded-md px-2 py-2 font-semibold hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {t("context.createOrg")}
        </Link>
      ) : (
        <span className="px-2 py-2 text-muted-foreground" aria-disabled="true">
          {t("context.createOrg")} · {t("context.offlineNeeded")}
        </span>
      )}
    </div>
  );
}

export function ContextSwitcher({ variant = "pill", showManagementLinks = false, className }: SwitcherProps) {
  const { t } = useTranslation();
  const { choices, active, isLoading, isError, refetch, setActive } = useChoices();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const activeValue = choiceValue(active);
  const activeLabel = contextTypeLabel(t, active);
  const showSkeleton = isLoading && choices.length <= 1;

  const select = (value: string) => {
    const choice = choices.find((c) => choiceValue(c) === value);
    if (choice) setActive(choice);
  };

  if (variant === "banner") {
    const Icon = ICONS[active.type];
    return (
      <Drawer open={drawerOpen} onOpenChange={setDrawerOpen}>
        <DrawerTrigger asChild>
          <button
            type="button"
            aria-label={t("context.activeAria", { name: active.name, type: activeLabel })}
            aria-haspopup="dialog"
            className={cn(
              "flex min-h-11 w-full items-center gap-2 border-b px-4 py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              active.type === "USER" ? "bg-muted" : "border-primary/30 bg-primary/10",
              isLoading && !active.confirmed && "animate-pulse",
              className,
            )}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block text-[11px] text-muted-foreground">{t("context.actAs")}</span>
              <span className="block truncate text-sm font-semibold text-foreground">
                {active.type === "USER" ? t("context.personalProfile") : active.name}
                {active.role && ` · ${t(`role.${active.role}`)}`}
              </span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          </button>
        </DrawerTrigger>
        <DrawerContent>
          <DrawerHeader>
            <DrawerTitle>{t("context.actAs")}</DrawerTitle>
            <DrawerDescription className="sr-only">{t("context.change")}</DrawerDescription>
          </DrawerHeader>
          <div className="max-h-[60vh] overflow-y-auto px-4 pb-4">
            {showSkeleton ? (
              <div className="space-y-2" aria-busy="true" aria-label={t("context.loading")}>
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-12 w-full rounded-xl" />
                ))}
              </div>
            ) : (
              <div role="radiogroup" aria-label={t("context.actAs")} className="space-y-1">
                {choices.map((choice) => {
                  const checked = choiceValue(choice) === activeValue;
                  return (
                    <button
                      key={choiceValue(choice)}
                      type="button"
                      role="radio"
                      aria-checked={checked}
                      onClick={() => {
                        select(choiceValue(choice));
                        setDrawerOpen(false);
                      }}
                      className={cn(
                        "flex min-h-12 w-full items-center gap-2 rounded-xl border px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        checked ? "border-primary bg-primary/5" : "border-transparent hover:bg-secondary",
                      )}
                    >
                      <ChoiceRow choice={choice} />
                      {checked && <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden />}
                    </button>
                  );
                })}
              </div>
            )}
            {isError && <LoadError onRetry={refetch} />}
            {showManagementLinks && (
              <>
                <div className="my-3 border-t" />
                <ManagementLinks onNavigate={() => setDrawerOpen(false)} />
              </>
            )}
          </div>
        </DrawerContent>
      </Drawer>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t("context.activeAria", { name: active.name, type: activeLabel })}
        aria-haspopup="menu"
        className={cn(
          "flex max-w-[14rem] items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isLoading && !active.confirmed && "animate-pulse",
          className,
        )}
      >
        <UserAvatar src={active.photo} name={active.name} size="sm" shape={active.type === "ORGANIZATION" ? "square" : "circle"} />
        <span className="min-w-0 leading-tight">
          <span className="block max-w-[10rem] truncate text-sm font-semibold text-foreground">{active.name}</span>
          <span className="block text-[11px] text-muted-foreground">{activeLabel}</span>
        </span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 rounded-xl p-1.5">
        <DropdownMenuLabel>{t("context.actAs")}</DropdownMenuLabel>
        {showSkeleton ? (
          <div className="space-y-2 p-1" aria-busy="true" aria-label={t("context.loading")}>
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full rounded-lg" />
            ))}
          </div>
        ) : (
          <DropdownMenuRadioGroup value={activeValue} onValueChange={select}>
            {choices.map((choice) => (
              <DropdownMenuRadioItem key={choiceValue(choice)} value={choiceValue(choice)} className="rounded-lg py-2 pl-8">
                <ChoiceRow choice={choice} />
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        )}
        {isError && <LoadError onRetry={refetch} />}
        {showManagementLinks && (
          <>
            <DropdownMenuSeparator />
            <ManagementLinks />
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
