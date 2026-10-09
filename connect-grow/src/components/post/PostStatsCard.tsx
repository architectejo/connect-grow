import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TrendingUp } from "lucide-react";
import type { Uuid } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { usePostStats } from "@/hooks/use-marketplace";

/** Vues des 30 derniers jours, visibles uniquement par le vendeur de l'annonce. */
export function PostStatsCard({ postId }: { postId: Uuid }) {
  const { data: history = [], isLoading } = usePostStats(postId, true);
  const total = history.reduce((sum, point) => sum + point.views, 0);

  return (
    <section aria-labelledby="stats-titre" className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="stats-titre" className="flex items-center gap-2 text-lg font-bold">
            <TrendingUp className="h-5 w-5 text-primary" aria-hidden /> Visibilité de votre annonce
          </h2>
          <p className="text-sm text-muted-foreground">30 derniers jours · visible par vous seul</p>
        </div>
        <p className="text-right">
          <span className="block font-display text-2xl font-extrabold tabular-nums">{total}</span>
          <span className="text-xs text-muted-foreground">vues</span>
        </p>
      </div>

      <div className="mt-5 h-52">
        {isLoading ? (
          <Skeleton className="h-full w-full rounded-xl" />
        ) : history.length === 0 ? (
          <p className="flex h-full items-center justify-center rounded-xl bg-muted text-sm text-muted-foreground">
            Pas encore de vues enregistrées.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="viewsFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="hsl(var(--border))" />
              <XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} minTickGap={16} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip
                cursor={{ stroke: "hsl(var(--primary))", strokeDasharray: "4 4" }}
                contentStyle={{
                  background: "hsl(var(--popover))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 12,
                  color: "hsl(var(--popover-foreground))",
                }}
                formatter={(value: number) => [`${value} vue${value > 1 ? "s" : ""}`, ""]}
                separator=""
              />
              <Area type="monotone" dataKey="views" stroke="hsl(var(--primary))" strokeWidth={2} fill="url(#viewsFill)" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
