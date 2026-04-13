import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  User, BarChart3, Bell, Repeat, LogOut, Plus, Eye, MousePointerClick,
  TrendingUp, Star, Package, MessageSquare, Clock, CheckCircle, XCircle
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar
} from "recharts";

// Mock data
const viewsData = Array.from({ length: 30 }, (_, i) => ({
  day: `${i + 1}/03`,
  views: Math.floor(Math.random() * 200 + 50 + (i > 15 && i < 22 ? 150 : 0)),
  boosted: i >= 15 && i < 22,
}));

const topPosts = [
  { title: "iPhone 14 Pro - Excellent état", views: 1240, rating: 4.8 },
  { title: "Service de maintenance informatique", views: 890, rating: 4.5 },
  { title: "Appartement T3 - Gombe", views: 650, rating: 4.2 },
];

const notifications = [
  { id: 1, message: "Nouvelle proposition d'échange reçue pour iPhone 14 Pro", time: "Il y a 5 min", read: false },
  { id: 2, message: "Votre publication a été vue 100 fois aujourd'hui", time: "Il y a 1h", read: false },
  { id: 3, message: "Paiement de 50$ reçu pour votre service", time: "Il y a 3h", read: true },
  { id: 4, message: "Nouvel avis 5 étoiles sur votre profil", time: "Hier", read: true },
];

const exchanges = [
  { id: 1, from: "Marie K.", item: "Samsung Galaxy S23", forItem: "iPhone 14 Pro", status: "pending" as const },
  { id: 2, from: "Paul M.", item: "MacBook Air", forItem: "Service web design", status: "accepted" as const },
  { id: 3, from: "Aline B.", item: "Vélo VTT", forItem: "Tablette iPad", status: "rejected" as const },
];

const statusConfig = {
  pending: { label: "En attente", icon: Clock, className: "text-warning" },
  accepted: { label: "Accepté", icon: CheckCircle, className: "text-success" },
  rejected: { label: "Refusé", icon: XCircle, className: "text-destructive" },
};

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState("profile");

  return (
    <div className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="sticky top-0 z-50 glass">
        <div className="container mx-auto flex items-center justify-between h-16 px-4">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">C+</span>
            </div>
            <span className="text-xl font-bold text-foreground">Connecte<span className="text-primary">+</span></span>
          </Link>
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm" asChild>
              <Link to="/">
                <Plus size={16} className="mr-1" /> Publier
              </Link>
            </Button>
            <Button variant="ghost" size="sm">
              <LogOut size={16} />
            </Button>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        {/* Profile header */}
        <div className="flex flex-col sm:flex-row items-start gap-6 mb-8">
          <div className="w-20 h-20 rounded-2xl gradient-primary flex items-center justify-center text-2xl font-bold text-primary-foreground">
            JK
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold text-foreground">Jean Kabila</h1>
              <span className="px-2.5 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-medium">
                Particulier
              </span>
              <span className="px-2.5 py-0.5 rounded-full bg-success/10 text-success text-xs font-medium flex items-center gap-1">
                <Star size={10} /> 4.6
              </span>
            </div>
            <p className="text-muted-foreground text-sm">Kinshasa, Gombe · Membre depuis mars 2024</p>
            <p className="text-sm text-foreground/80 mt-2 max-w-lg">
              Passionné de technologie et de commerce local. Toujours à la recherche de bonnes affaires !
            </p>
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid grid-cols-4 w-full max-w-lg mb-8">
            <TabsTrigger value="profile" className="flex items-center gap-1.5 text-xs">
              <User size={14} /> Profil
            </TabsTrigger>
            <TabsTrigger value="stats" className="flex items-center gap-1.5 text-xs">
              <BarChart3 size={14} /> Stats
            </TabsTrigger>
            <TabsTrigger value="notifications" className="flex items-center gap-1.5 text-xs">
              <Bell size={14} /> Notifs
            </TabsTrigger>
            <TabsTrigger value="exchanges" className="flex items-center gap-1.5 text-xs">
              <Repeat size={14} /> Échanges
            </TabsTrigger>
          </TabsList>

          {/* Profile tab */}
          <TabsContent value="profile">
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-foreground">Mes publications</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {topPosts.map((post) => (
                  <div key={post.title} className="p-5 rounded-xl bg-card border border-border shadow-card">
                    <div className="w-full h-32 rounded-lg bg-muted mb-4 flex items-center justify-center">
                      <Package size={32} className="text-muted-foreground" />
                    </div>
                    <h3 className="font-medium text-foreground text-sm">{post.title}</h3>
                    <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1"><Eye size={12} /> {post.views}</span>
                      <span className="flex items-center gap-1"><Star size={12} /> {post.rating}</span>
                    </div>
                  </div>
                ))}
              </div>

              <h2 className="text-lg font-semibold text-foreground pt-4">Avis reçus</h2>
              <div className="space-y-3">
                {[
                  { author: "Marie K.", rating: 5, text: "Excellent vendeur, produit conforme !" },
                  { author: "Paul M.", rating: 4, text: "Bon service, livraison un peu longue." },
                ].map((review) => (
                  <div key={review.author} className="p-4 rounded-xl bg-card border border-border shadow-card flex gap-4">
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground">
                      {review.author[0]}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-foreground">{review.author}</span>
                        <span className="flex items-center gap-0.5 text-warning text-xs">
                          {Array.from({ length: review.rating }).map((_, i) => (
                            <Star key={i} size={10} fill="currentColor" />
                          ))}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">{review.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </TabsContent>

          {/* Stats tab */}
          <TabsContent value="stats">
            <div className="space-y-6">
              {/* KPIs */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { label: "Vues totales", value: "3,240", icon: Eye, change: "+12%" },
                  { label: "Clics contact", value: "156", icon: MousePointerClick, change: "+8%" },
                  { label: "Note moyenne", value: "4.6", icon: Star, change: "+0.2" },
                  { label: "Croissance", value: "+25%", icon: TrendingUp, change: "vs mois dernier" },
                ].map((kpi) => (
                  <div key={kpi.label} className="p-5 rounded-xl bg-card border border-border shadow-card">
                    <div className="flex items-center justify-between mb-3">
                      <kpi.icon size={18} className="text-primary" />
                      <span className="text-xs text-success font-medium">{kpi.change}</span>
                    </div>
                    <p className="text-2xl font-bold text-foreground">{kpi.value}</p>
                    <p className="text-xs text-muted-foreground mt-1">{kpi.label}</p>
                  </div>
                ))}
              </div>

              {/* Views chart */}
              <div className="p-6 rounded-xl bg-card border border-border shadow-card">
                <h3 className="text-base font-semibold text-foreground mb-4">Visibilité — 30 derniers jours</h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={viewsData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(214, 20%, 88%)" />
                      <XAxis dataKey="day" tick={{ fontSize: 11 }} stroke="hsl(215, 12%, 50%)" />
                      <YAxis tick={{ fontSize: 11 }} stroke="hsl(215, 12%, 50%)" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(0, 0%, 100%)",
                          border: "1px solid hsl(214, 20%, 88%)",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="views"
                        stroke="hsl(215, 80%, 48%)"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: "hsl(215, 80%, 48%)" }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="text-xs text-muted-foreground mt-3 flex items-center gap-1">
                  <span className="w-3 h-1 rounded bg-primary inline-block" /> Période boostée (16–22 mars)
                </p>
              </div>

              {/* Top posts */}
              <div className="p-6 rounded-xl bg-card border border-border shadow-card">
                <h3 className="text-base font-semibold text-foreground mb-4">Top publications</h3>
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topPosts}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(214, 20%, 88%)" />
                      <XAxis dataKey="title" tick={{ fontSize: 10 }} stroke="hsl(215, 12%, 50%)" />
                      <YAxis tick={{ fontSize: 11 }} stroke="hsl(215, 12%, 50%)" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(0, 0%, 100%)",
                          border: "1px solid hsl(214, 20%, 88%)",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                      />
                      <Bar dataKey="views" fill="hsl(200, 70%, 50%)" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Notifications tab */}
          <TabsContent value="notifications">
            <div className="space-y-3">
              {notifications.map((notif) => (
                <div
                  key={notif.id}
                  className={`p-4 rounded-xl border shadow-card flex items-start gap-3 ${
                    notif.read ? "bg-card border-border" : "bg-primary/5 border-primary/20"
                  }`}
                >
                  <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${notif.read ? "bg-transparent" : "bg-primary"}`} />
                  <div className="flex-1">
                    <p className={`text-sm ${notif.read ? "text-muted-foreground" : "text-foreground font-medium"}`}>
                      {notif.message}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">{notif.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </TabsContent>

          {/* Exchanges tab */}
          <TabsContent value="exchanges">
            <div className="space-y-3">
              {exchanges.map((exchange) => {
                const config = statusConfig[exchange.status];
                return (
                  <div key={exchange.id} className="p-5 rounded-xl bg-card border border-border shadow-card">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-foreground">{exchange.from}</span>
                      <span className={`flex items-center gap-1 text-xs font-medium ${config.className}`}>
                        <config.icon size={14} /> {config.label}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <span className="px-2 py-1 bg-muted rounded text-xs">{exchange.item}</span>
                      <Repeat size={14} className="text-primary" />
                      <span className="px-2 py-1 bg-muted rounded text-xs">{exchange.forItem}</span>
                    </div>
                    {exchange.status === "pending" && (
                      <div className="flex gap-2 mt-4">
                        <Button size="sm" className="flex-1">Accepter</Button>
                        <Button size="sm" variant="outline" className="flex-1">Refuser</Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default Dashboard;
