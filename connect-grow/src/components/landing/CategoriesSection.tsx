import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useCategories } from "@/hooks/use-marketplace";
import { categoryIcon } from "@/lib/category-icons";

/** Accès direct aux catégories gérées dans le back-office. */
const CategoriesSection = () => {
  const { t } = useTranslation();
  const { data: categories = [], isLoading, isError } = useCategories();

  if (isError || (!isLoading && categories.length === 0)) return null;

  return (
    <section id="categories" className="py-12 md:py-16">
      <div className="container">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">{t("landing.categories.eyebrow")}</p>
            <h2 className="mt-1.5 text-2xl font-extrabold md:text-3xl">{t("landing.categories.title")}</h2>
          </div>
          <Link
            to="/marketplace"
            className="hidden items-center gap-1 text-sm font-semibold text-primary hover:underline sm:inline-flex"
          >
            {t("landing.categories.seeAll")} <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>

        {/* Défilement horizontal sur mobile, grille sur grand écran */}
        <ul className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2 scrollbar-none md:mx-0 md:grid md:grid-cols-4 md:overflow-visible md:px-0 lg:grid-cols-8">
          {isLoading
            ? Array.from({ length: 8 }, (_, i) => (
                <li key={i} className="shrink-0">
                  <Skeleton className="h-28 w-28 rounded-2xl md:w-full" />
                </li>
              ))
            : categories.map((category) => {
                const Icon = categoryIcon(category);
                return (
                  <li key={category.id} className="shrink-0 snap-start">
                    <Link
                      to={`/marketplace?category=${category.id}`}
                      className="group flex h-28 w-28 flex-col items-center justify-center gap-2.5 rounded-2xl border bg-card p-3 text-center shadow-soft transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-card md:w-full"
                    >
                      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:gradient-primary group-hover:text-primary-foreground">
                        <Icon className="h-5 w-5" aria-hidden />
                      </span>
                      <span className="line-clamp-2 text-xs font-semibold leading-tight text-foreground">{category.name}</span>
                    </Link>
                  </li>
                );
              })}
        </ul>
      </div>
    </section>
  );
};

export default CategoriesSection;
