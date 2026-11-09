import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BadgeCheck, MessageCircleHeart, Search, ShieldCheck, Sparkles, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { useCategories } from "@/hooks/use-marketplace";

const promises = [
  { icon: Star, labelKey: "landing.hero.promiseRated" },
  { icon: BadgeCheck, labelKey: "landing.hero.promiseVerification" },
  { icon: Sparkles, labelKey: "landing.hero.promiseFree" },
] as const;

/** Illustration d'un profil avec une note du vendeur : purement décorative, masquée aux lecteurs d'écran. */
const ReviewIllustration = () => {
  const { t } = useTranslation();
  return (
  <div className="relative mx-auto w-full max-w-sm" aria-hidden>
    <div className="absolute -inset-10 rounded-full bg-primary/30 blur-3xl" />
    <div className="relative rotate-2 rounded-2xl border border-white/10 bg-card p-5 text-card-foreground shadow-lifted">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl gradient-primary font-display text-lg font-extrabold text-primary-foreground">
          B
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display font-bold">{t("landing.hero.shopName")}</p>
          <p className="text-xs text-muted-foreground">{t("landing.hero.shopLocation")}</p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-1 text-[11px] font-semibold text-success ring-1 ring-inset ring-success/25">
          <BadgeCheck className="h-3 w-3" /> {t("landing.hero.rccm")}
        </span>
      </div>
      <div className="mt-4 flex items-end justify-between rounded-xl bg-muted p-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{t("landing.hero.sellerRating")}</p>
          <p className="font-display text-3xl font-extrabold tabular-nums">4,8</p>
        </div>
        <div className="flex gap-0.5 pb-1.5">
          {[0, 1, 2, 3, 4].map((i) => (
            <Star key={i} className="h-4 w-4 fill-sun text-sun" />
          ))}
        </div>
      </div>
    </div>
    <div className="relative -mt-6 ml-10 -rotate-3 rounded-2xl border border-white/10 bg-card p-4 text-card-foreground shadow-lifted">
      <div className="flex items-center gap-2">
        <MessageCircleHeart className="h-5 w-5 text-primary" />
        <p className="text-sm font-semibold">{t("landing.hero.reviewTitle")}</p>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        {t("landing.hero.reviewText")}
      </p>
    </div>
  </div>
  );
};

const HeroSection = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: categories = [] } = useCategories();
  const [search, setSearch] = useState("");
  const [commune, setCommune] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams();
    if (search.trim()) params.set("search", search.trim());
    if (commune) params.set("commune", commune);
    const query = params.toString();
    navigate(`/marketplace${query ? `?${query}` : ""}`);
  };

  return (
    <section className="relative overflow-hidden gradient-hero text-white">
      {/* Halos décoratifs en CSS : aucune image à télécharger (réseau 3G) */}
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute -left-32 top-10 h-80 w-80 rounded-full bg-primary/40 blur-3xl" />
        <div className="absolute -right-20 bottom-0 h-72 w-72 rounded-full bg-sun/20 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage: "radial-gradient(circle at 1px 1px, white 1px, transparent 0)",
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      <div className="container relative grid items-center gap-12 pb-16 pt-28 md:pb-24 md:pt-36 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="animate-fade-in">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3.5 py-1.5 text-xs font-semibold text-white/90 backdrop-blur-sm sm:text-sm">
            <span className="h-2 w-2 rounded-full bg-sun" aria-hidden />
            {t("brand.location")}
          </p>

          <h1 className="mt-5 text-balance font-display text-4xl font-extrabold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
            {t("landing.hero.titleStart")} <span className="text-sun">{t("landing.hero.titleEnd")}</span>
          </h1>

          <p className="mt-5 max-w-xl text-base leading-relaxed text-white/75 sm:text-lg">
            {t("landing.hero.subtitle")}
          </p>

          <form
            onSubmit={handleSubmit}
            role="search"
            className="mt-8 grid gap-2 rounded-2xl bg-card p-2 text-card-foreground shadow-lifted sm:grid-cols-[1fr_auto_auto]"
          >
            <label className="relative flex items-center">
              <span className="sr-only">{t("landing.hero.searchLabel")}</span>
              <Search className="pointer-events-none absolute left-3.5 h-5 w-5 text-muted-foreground" aria-hidden />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("landing.hero.searchPlaceholder")}
                className="h-12 w-full rounded-xl bg-transparent pl-11 pr-3 text-base outline-none placeholder:text-muted-foreground focus-visible:ring-0"
                enterKeyHint="search"
              />
            </label>
            <CommuneSelect
              value={commune}
              onChange={setCommune}
              placeholder={t("landing.hero.allCity")}
              aria-label={t("landing.hero.commune")}
              className="h-12 rounded-xl border-0 bg-muted sm:w-48"
            />
            <Button type="submit" size="lg" className="h-12 shadow-glow">
              <Search aria-hidden /> {t("landing.hero.search")}
            </Button>
          </form>

          {categories.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-white/60">{t("landing.hero.popular")}</span>
              {categories.slice(0, 4).map((category) => (
                <Link
                  key={category.id}
                  to={`/marketplace?category=${category.id}`}
                  className="rounded-full border border-white/15 px-3 py-1 text-white/85 transition-colors hover:bg-white/10 hover:text-white"
                >
                  {category.name}
                </Link>
              ))}
            </div>
          )}

          <ul className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-x-6">
            {promises.map(({ icon: Icon, labelKey }) => (
              <li key={labelKey} className="flex items-center gap-2 text-sm font-medium text-white/80">
                <Icon className="h-4 w-4 text-sun" aria-hidden />
                {t(labelKey)}
              </li>
            ))}
          </ul>
        </div>

        <div className="hidden lg:block">
          <ReviewIllustration />
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
