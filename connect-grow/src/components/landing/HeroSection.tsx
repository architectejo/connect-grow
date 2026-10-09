import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BadgeCheck, MessageCircleHeart, Search, ShieldCheck, Sparkles, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { useCategories } from "@/hooks/use-marketplace";

const promises = [
  { icon: Star, label: "Vendeurs notés par de vrais acheteurs" },
  { icon: BadgeCheck, label: "Boutiques vérifiées" },
  { icon: Sparkles, label: "Publication gratuite" },
];

/** Illustration de la carte de confiance : purement décorative, masquée aux lecteurs d'écran. */
const TrustIllustration = () => (
  <div className="relative mx-auto w-full max-w-sm" aria-hidden>
    <div className="absolute -inset-10 rounded-full bg-primary/30 blur-3xl" />
    <div className="relative rotate-2 rounded-2xl border border-white/10 bg-card p-5 text-card-foreground shadow-lifted">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl gradient-primary font-display text-lg font-extrabold text-primary-foreground">
          B
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display font-bold">Votre boutique</p>
          <p className="text-xs text-muted-foreground">Gombe, Kinshasa</p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-1 text-[11px] font-semibold text-success ring-1 ring-inset ring-success/25">
          <BadgeCheck className="h-3 w-3" /> Vérifié
        </span>
      </div>
      <div className="mt-4 flex items-end justify-between rounded-xl bg-muted p-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">Note de confiance</p>
          <p className="font-display text-3xl font-extrabold tabular-nums">4,8</p>
        </div>
        <div className="flex gap-0.5 pb-1.5">
          {[0, 1, 2, 3, 4].map((i) => (
            <Star key={i} className="h-4 w-4 fill-sun text-sun" />
          ))}
        </div>
      </div>
      <span className="mt-3 inline-flex items-center gap-1 rounded-full bg-success/10 px-2.5 py-1.5 text-xs font-semibold text-success ring-1 ring-inset ring-success/25">
        <ShieldCheck className="h-3.5 w-3.5" /> Vendeur fiable
      </span>
    </div>
    <div className="relative -mt-6 ml-10 -rotate-3 rounded-2xl border border-white/10 bg-card p-4 text-card-foreground shadow-lifted">
      <div className="flex items-center gap-2">
        <MessageCircleHeart className="h-5 w-5 text-primary" />
        <p className="text-sm font-semibold">Avis après une affaire conclue</p>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        Seuls les acheteurs qui ont réellement traité avec le vendeur peuvent le noter.
      </p>
    </div>
  </div>
);

const HeroSection = () => {
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
            Kinshasa · 24 communes
          </p>

          <h1 className="mt-5 text-balance font-display text-4xl font-extrabold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
            Achetez et vendez près de chez vous, <span className="text-sun">en toute confiance.</span>
          </h1>

          <p className="mt-5 max-w-xl text-base leading-relaxed text-white/75 sm:text-lg">
            Des annonces claires, filtrables par commune et par prix, et des vendeurs dont la réputation se vérifie avant
            de les contacter.
          </p>

          <form
            onSubmit={handleSubmit}
            role="search"
            className="mt-8 grid gap-2 rounded-2xl bg-card p-2 text-card-foreground shadow-lifted sm:grid-cols-[1fr_auto_auto]"
          >
            <label className="relative flex items-center">
              <span className="sr-only">Que cherchez-vous ?</span>
              <Search className="pointer-events-none absolute left-3.5 h-5 w-5 text-muted-foreground" aria-hidden />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Téléphone, pagne, plombier…"
                className="h-12 w-full rounded-xl bg-transparent pl-11 pr-3 text-base outline-none placeholder:text-muted-foreground focus-visible:ring-0"
                enterKeyHint="search"
              />
            </label>
            <CommuneSelect
              value={commune}
              onChange={setCommune}
              placeholder="Toute la ville"
              aria-label="Commune"
              className="h-12 rounded-xl border-0 bg-muted sm:w-48"
            />
            <Button type="submit" size="lg" className="h-12 shadow-glow">
              <Search aria-hidden /> Rechercher
            </Button>
          </form>

          {categories.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-white/60">Populaire :</span>
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
            {promises.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-2 text-sm font-medium text-white/80">
                <Icon className="h-4 w-4 text-sun" aria-hidden />
                {label}
              </li>
            ))}
          </ul>
        </div>

        <div className="hidden lg:block">
          <TrustIllustration />
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
