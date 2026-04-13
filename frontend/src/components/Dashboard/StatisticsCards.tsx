import { Activity, Gauge, Sparkles, Timer } from "lucide-react";
import Card from "../Common/Card";
import type { ProgressSummary } from "../../types";

interface StatisticsCardsProps {
  summary: ProgressSummary;
}

export default function StatisticsCards({ summary }: StatisticsCardsProps) {
  const items = [
    {
      label: "Sessions",
      value: summary.total_sessions,
      sub: `${summary.completed_sessions} completed`,
      icon: Activity,
    },
    {
      label: "Avg clarity",
      value: `${Math.round(summary.avg_clarity_score)}/100`,
      sub: `Best ${Math.round(summary.best_clarity)}`,
      icon: Sparkles,
    },
    {
      label: "Avg pace",
      value: `${Math.round(summary.avg_speaking_pace)} wpm`,
      sub: `Best ${Math.round(summary.best_pace)}`,
      icon: Gauge,
    },
    {
      label: "Total time",
      value: `${Math.round(summary.total_duration_seconds / 60)} min`,
      sub: `${summary.total_filler_words} fillers`,
      icon: Timer,
    },
  ];

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map(({ label, value, sub, icon: Icon }) => (
        <Card key={label} padding="p-5">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs uppercase tracking-wider text-slate-400">
                {label}
              </div>
              <div className="mt-2 text-2xl font-bold">{value}</div>
              <div className="text-xs text-slate-500 mt-1">{sub}</div>
            </div>
            <div className="w-10 h-10 rounded-xl bg-primary-500/20 flex items-center justify-center text-primary-200">
              <Icon className="w-5 h-5" />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
