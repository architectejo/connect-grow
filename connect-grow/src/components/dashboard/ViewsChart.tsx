import { useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDayMonth } from "@/lib/format";
import type { ViewStatPoint } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const RANGES = [
  { days: 7, label: "7 jours" },
  { days: 30, label: "30 jours" },
] as const;

/**
 * L'API ne renvoie que les jours avec au moins une vue (format « jj/MM ») :
 * on complète les jours manquants à 0 pour que la courbe ne mente pas sur le temps.
 */
function fillDays(history: ViewStatPoint[], days: number): ViewStatPoint[] {
  const byDay = new Map(history.map((point) => [point.day, point.views]));
  const now = Date.now();
  return Array.from({ length: days }, (_, i) => {
    // Jours calculés à l'heure de Kinshasa, comme côté serveur (pas de décalage selon l'appareil)
    const day = formatDayMonth(new Date(now - (days - 1 - i) * 86_400_000));
    return { day, views: byDay.get(day) ?? 0 };
  });
}

interface ViewsChartProps {
  history: ViewStatPoint[];
  isLoading?: boolean;
}

/** Évolution des vues de toutes les annonces du vendeur (CDC 3.9). Une seule série : pas de légende. */
export function ViewsChart({ history, isLoading }: ViewsChartProps) {
  const [days, setDays] = useState<7 | 30>(30);
  const [showTable, setShowTable] = useState(false);
  const data = useMemo(() => fillDays(history, days), [history, days]);
  const total = data.reduce((sum, point) => sum + point.views, 0);

  return (
    <section aria-labelledby="vues-titre" className="rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="vues-titre" className="text-lg font-bold">
            Vues de vos annonces
          </h2>
          <p className="text-sm text-muted-foreground">
            <span className="font-semibold tabular-nums text-foreground">{total}</span> vue{total > 1 ? "s" : ""} sur les{" "}
            {days} derniers jours
          </p>
        </div>
        <div role="radiogroup" aria-label="Période" className="flex rounded-lg bg-muted p-1">
          {RANGES.map((range) => (
            <button
              key={range.days}
              type="button"
              role="radio"
              aria-checked={days === range.days}
              onClick={() => setDays(range.days)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                days === range.days ? "bg-card text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 h-60">
        {isLoading ? (
          <Skeleton className="h-full w-full rounded-xl" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 6, right: 6, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="dashboardViewsFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeOpacity={0.7} />
              <XAxis
                dataKey="day"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                interval={days === 7 ? 0 : "preserveStartEnd"}
                minTickGap={20}
              />
              <YAxis
                allowDecimals={false}
                tickLine={false}
                axisLine={false}
                width={40}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              />
              <Tooltip
                cursor={{ stroke: "hsl(var(--muted-foreground))", strokeWidth: 1, strokeDasharray: "3 3" }}
                contentStyle={{
                  background: "hsl(var(--popover))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 12,
                  boxShadow: "var(--shadow-md)",
                  color: "hsl(var(--popover-foreground))",
                  fontSize: 13,
                }}
                labelStyle={{ color: "hsl(var(--muted-foreground))", marginBottom: 2 }}
                formatter={(value: number) => [`${value} vue${value > 1 ? "s" : ""}`, ""]}
                separator=""
              />
              <Area
                type="monotone"
                dataKey="views"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                fill="url(#dashboardViewsFill)"
                activeDot={{ r: 5, strokeWidth: 2, stroke: "hsl(var(--card))", fill: "hsl(var(--primary))" }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Vue tableau : accès aux valeurs sans le graphique (lecteurs d'écran, lecture précise) */}
      <button
        type="button"
        onClick={() => setShowTable((v) => !v)}
        aria-expanded={showTable}
        className="mt-3 text-xs font-semibold text-primary hover:underline"
      >
        {showTable ? "Masquer le tableau" : "Afficher sous forme de tableau"}
      </button>
      {showTable && (
        <div className="mt-3 max-h-60 overflow-y-auto rounded-xl border">
          <table className="w-full text-sm">
            <caption className="sr-only">Vues par jour</caption>
            <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Jour
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">
                  Vues
                </th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().map((point) => (
                <tr key={point.day} className="border-t">
                  <td className="px-3 py-1.5">{point.day}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{point.views}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
