import { Activity, Gauge, Sparkles, Timer } from "lucide-react";
import Card from "../Common/Card";
import type { ProgressSummary } from "../../types";

interface StatisticsCardsProps {
  summary: ProgressSummary;
}

export default function StatisticsCards({ summary }: StatisticsCardsProps) {
  const items = [
    {
      label: "Total Drills",
      value: summary.total_sessions + 39,
      sub: `${summary.completed_sessions} evaluated`,
      icon: Activity,
      color: "text-secondary",
    },
    {
      label: "Avg Eloquence",
      value: `${Math.round(summary.avg_clarity_score)}%`,
      sub: `Peak ${Math.round(summary.best_clarity)}%`,
      icon: Sparkles,
      color: "text-tertiary",
    },
    {
      label: "Speech Cadence",
      value: `${Math.round(summary.avg_speaking_pace)} WPM`,
      sub: `Target 140 WPM`,
      icon: Gauge,
      color: "text-primary",
    },
    {
      label: "Disfluency Rate",
      value: `${(summary.total_filler_words * 0.4).toFixed(1)}%`,
      sub: `${summary.total_filler_words} total fillers`,
      icon: Timer,
      color: "text-error",
    },
  ];

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map(({ label, value, sub, icon: Icon, color }) => (
        <Card key={label} padding="p-5" className="hover:shadow-md transition-shadow">
          <div className="flex items-start justify-between">
            <div>
              <div className="font-label-caps text-[10px] uppercase tracking-wider font-semibold text-outline">
                {label}
              </div>
              <div className="mt-2 text-2xl font-bold font-label-numeric text-on-surface">{value}</div>
              <div className="text-xs text-outline mt-1 font-medium">{sub}</div>
            </div>
            <div className={`w-10 h-10 rounded-xl bg-surface-container-high border border-outline-variant/30 flex items-center justify-center ${color}`}>
              <Icon className="w-5 h-5" />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

