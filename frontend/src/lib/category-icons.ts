import {
  Baby,
  BookOpen,
  Car,
  Dumbbell,
  Hammer,
  Home,
  Laptop,
  type LucideIcon,
  Shirt,
  ShoppingBag,
  Smartphone,
  Sofa,
  Sparkles,
  Tag,
  Tractor,
  Utensils,
  Wrench,
} from "lucide-react";

// Icônes connues : nom Lucide saisi dans le back-office (champ Category.icon) ou mot-clé du slug.
// Liste courte volontairement : importer toutes les icônes Lucide alourdirait l'application.
const ICONS: Record<string, LucideIcon> = {
  smartphone: Smartphone,
  phone: Smartphone,
  telephone: Smartphone,
  electronique: Laptop,
  laptop: Laptop,
  informatique: Laptop,
  car: Car,
  vehicule: Car,
  auto: Car,
  home: Home,
  immobilier: Home,
  maison: Home,
  shirt: Shirt,
  mode: Shirt,
  vetement: Shirt,
  "book-open": BookOpen,
  education: BookOpen,
  livre: BookOpen,
  wrench: Wrench,
  service: Wrench,
  hammer: Hammer,
  bricolage: Hammer,
  dumbbell: Dumbbell,
  sport: Dumbbell,
  utensils: Utensils,
  alimentation: Utensils,
  restauration: Utensils,
  sofa: Sofa,
  meuble: Sofa,
  beaute: Sparkles,
  sparkles: Sparkles,
  baby: Baby,
  enfant: Baby,
  agriculture: Tractor,
  "shopping-bag": ShoppingBag,
};

const normalize = (value: string) =>
  value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");

export function categoryIcon(category: { icon?: string; slug?: string; name?: string }): LucideIcon {
  if (category.icon && ICONS[category.icon]) return ICONS[category.icon];
  const haystack = normalize(`${category.slug ?? ""} ${category.name ?? ""}`);
  const match = Object.keys(ICONS).find((key) => haystack.includes(key));
  return match ? ICONS[match] : Tag;
}
