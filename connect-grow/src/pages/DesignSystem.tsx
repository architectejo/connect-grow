import { Plus, Search } from "lucide-react";
import type { Post, Seller } from "@/api/types";
import { Button } from "@/components/ui/button";
import { AppShell } from "@/components/layout/AppShell";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  PostCard,
  PostGrid,
  PostGridSkeleton,
  PriceTag,
  SellerCard,
  RatingBlock,
  RatingValue,
  StatusBadge,
} from "@/components/common";

// Galerie de développement (route /design, absente du build de production).
// Les données ci-dessous sont des exemples d'affichage, pas des données réelles.

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

const sellers: Record<string, Seller> = {
  business: {
    id: "1",
    full_name: "Patrick Ilunga",
    user_type: "ENTREPRISE",
    business_profile: { business_name: "Gombe Électronique", is_verified: true, logo: null },
    date_joined: "2025-03-12T10:00:00Z",
  },
  person: {
    id: "2",
    full_name: "Grâce Mbuyi",
    user_type: "PARTICULIER",
    date_joined: "2026-06-02T10:00:00Z",
  },
  newbie: {
    id: "3",
    full_name: "Junior Kabasele",
    user_type: "PARTICULIER",
    date_joined: "2026-09-01T10:00:00Z",
  },
};

const basePost = {
  allowed_channels: ["MESSAGE" as const],
  category: "cat-1",
  commune: "com-1",
  description: "",
  views_count: 0,
  likes_count: 0,
  main_image: null,
};

const samplePosts: Post[] = [
  {
    ...basePost,
    id: "101",
    seller: sellers.business,
    post_type: "PRODUIT",
    title: "iPhone 14 Pro 256 Go, excellent état, avec facture",
    price: "850",
    currency: "USD",
    condition: "OCCASION",
    is_price_negotiable: true,
    commune_name: "Gombe",
    created_at: hoursAgo(3),
    badges: ["trending"],
  },
  {
    ...basePost,
    id: "102",
    seller: sellers.person,
    post_type: "PRODUIT",
    title: "Pagnes wax hollandais, lot de 6 yards",
    price: "95000",
    currency: "CDF",
    condition: "NEUF",
    is_exchangeable: true,
    commune_name: "Lingwala",
    created_at: hoursAgo(26),
  },
  {
    ...basePost,
    id: "103",
    seller: sellers.newbie,
    post_type: "SERVICE",
    title: "Plombier disponible 7j/7, dépannage rapide",
    price: "25",
    currency: "USD",
    is_price_negotiable: true,
    commune_name: "Limete",
    created_at: hoursAgo(50),
  },
  {
    ...basePost,
    id: "104",
    seller: sellers.business,
    post_type: "PRODUIT",
    title: "Groupe électrogène 5 kVA silencieux",
    price: "1200",
    currency: "USD",
    condition: "NEUF",
    commune_name: "Ngaliema",
    created_at: hoursAgo(120),
    badges: ["sponsored"],
  },
];

const colorTokens = [
  { name: "primary", className: "bg-primary text-primary-foreground" },
  { name: "sun", className: "bg-sun text-sun-foreground" },
  { name: "success", className: "bg-success text-success-foreground" },
  { name: "info", className: "bg-info text-info-foreground" },
  { name: "warning", className: "bg-warning text-warning-foreground" },
  { name: "destructive", className: "bg-destructive text-destructive-foreground" },
  { name: "secondary", className: "bg-secondary text-secondary-foreground" },
  { name: "muted", className: "bg-muted text-muted-foreground" },
  { name: "card", className: "bg-card text-card-foreground border" },
];

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="space-y-4 border-t py-10 first:border-t-0 first:pt-0">
    <h2 className="text-xl font-bold">{title}</h2>
    {children}
  </section>
);

const DesignSystem = () => (
  <AppShell>
    <PageHeader
      eyebrow="Phase 0 · Fondations"
      title="Design system Connecte+"
      description="Tokens, composants métier et états d'interface. Basculez le thème clair/sombre et réduisez la fenêtre pour vérifier le rendu mobile."
      actions={
        <>
          <Button variant="outline">
            <Search aria-hidden /> Secondaire
          </Button>
          <Button className="shadow-glow">
            <Plus aria-hidden /> Publier
          </Button>
        </>
      }
    />

    <Section title="Couleurs">
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-9">
        {colorTokens.map((token) => (
          <div key={token.name} className={`flex h-20 items-end rounded-xl p-2.5 text-xs font-semibold ${token.className}`}>
            {token.name}
          </div>
        ))}
      </div>
    </Section>

    <Section title="Typographie">
      <div className="space-y-3">
        <p className="font-display text-4xl font-extrabold tracking-tight md:text-5xl">Achetez près de chez vous</p>
        <p className="font-display text-2xl font-bold">Titre de section — Plus Jakarta Sans</p>
        <p className="max-w-2xl text-base text-muted-foreground">
          Texte courant en Inter. Les annonces sont structurées, filtrables par commune et par prix, et chaque vendeur
          affiche une réputation vérifiable.
        </p>
      </div>
    </Section>

    <Section title="Boutons">
      <div className="flex flex-wrap gap-3">
        <Button>Principal</Button>
        <Button variant="sun">Mise en avant</Button>
        <Button variant="soft">Doux</Button>
        <Button variant="outline">Contour</Button>
        <Button variant="ghost">Fantôme</Button>
        <Button variant="destructive">Supprimer</Button>
        <Button size="lg" className="shadow-glow">
          Grand bouton
        </Button>
      </div>
    </Section>

    <Section title="Prix, confiance et badges">
      <div className="flex flex-wrap items-center gap-6">
        <PriceTag amount="850" currency="USD" negotiable size="lg" />
        <PriceTag amount="95000" currency="CDF" size="lg" />
      </div>
      <div className="flex flex-wrap items-center gap-6">
        <RatingValue kind="offer" rating={{ average: 4.2, count: 5 }} />
        <RatingValue kind="offer" rating={{ average: null, count: 2 }} />
        <RatingValue kind="offer" rating={{ average: null, count: 0 }} />
        <RatingBlock kind="offer" rating={{ average: 4.2, count: 5 }} />
        <RatingBlock kind="seller" rating={{ average: 3.9, count: 8 }} footer="Sur Connecte+ depuis mars 2025" />
        <RatingBlock kind="seller" rating={{ average: null, count: 2 }} />
      </div>
      <div className="flex flex-wrap gap-2">
        {(["verified", "trending", "sponsored", "exchangeable", "service", "NEUF", "OCCASION", "RECONDITIONNE"] as const).map(
          (kind) => (
            <StatusBadge key={kind} kind={kind} size="md" />
          ),
        )}
      </div>
    </Section>

    <Section title="Cartes d'annonce">
      <PostGrid>
        {samplePosts.map((post, i) => (
          <PostCard key={post.id} post={post} isFavorite={i === 1} onToggleFavorite={() => undefined} />
        ))}
      </PostGrid>
    </Section>

    <Section title="Chargement (skeletons)">
      <PostGridSkeleton count={4} />
    </Section>

    <Section title="Carte vendeur">
      <div className="grid gap-4 md:grid-cols-3">
        <SellerCard
          seller={sellers.business}
          actions={
            <>
              <Button>Contacter</Button>
              <Button variant="outline">Voir la boutique</Button>
            </>
          }
        />
        <SellerCard seller={sellers.person} />
        <SellerCard seller={sellers.newbie} />
      </div>
    </Section>

    <Section title="États vide et erreur">
      <div className="grid gap-4 md:grid-cols-2">
        <EmptyState
          icon={Search}
          title="Aucune annonce à Kintambo"
          description="Élargissez la recherche à toute la ville ou publiez la première annonce de votre commune."
          action={<Button variant="outline">Élargir la recherche</Button>}
        />
        <ErrorState onRetry={() => undefined} />
      </div>
    </Section>
  </AppShell>
);

export default DesignSystem;
