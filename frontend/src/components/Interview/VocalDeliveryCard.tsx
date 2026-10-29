import type { VocalDelivery } from "../../types";

interface VocalDeliveryCardProps {
  vocalDelivery?: VocalDelivery | null;
  accent?: "primary" | "secondary" | "tertiary";
}

const ACCENTS = {
  primary: {
    border: "border-primary/30",
    bg: "bg-primary/10",
    text: "text-primary",
    bar: "bg-primary",
  },
  secondary: {
    border: "border-secondary/30",
    bg: "bg-secondary/10",
    text: "text-secondary",
    bar: "bg-secondary",
  },
  tertiary: {
    border: "border-tertiary/30",
    bg: "bg-tertiary/10",
    text: "text-tertiary",
    bar: "bg-tertiary",
  },
};

function levelLabel(score: number, lowLabel: string, highLabel: string) {
  if (score >= 70) return highLabel;
  if (score >= 40) return "Moderate";
  return lowLabel;
}

export default function VocalDeliveryCard({
  vocalDelivery,
  accent = "secondary",
}: VocalDeliveryCardProps) {
  const summary = vocalDelivery?.summary;
  if (!summary) return null;

  const theme = ACCENTS[accent];
  const confidence = Math.round(summary.confidence_score ?? 0);
  const nervousness = Math.round(summary.nervousness_score ?? 0);
  const composure = Math.round(summary.composure_score ?? 0);
  const timeline = vocalDelivery?.timeline ?? [];

  const sampledTimeline =
    timeline.length > 48
      ? timeline.filter(
          (_, index) => index % Math.ceil(timeline.length / 48) === 0
        )
      : timeline;

  const metrics = [
    {
      key: "confidence",
      label: "Confidence Score",
      value: confidence,
      caption: levelLabel(confidence, "Low", "High"),
      color: "text-emerald-400",
      bar: "bg-emerald-400",
      ring: "border-emerald-500/30 bg-emerald-500/10",
      icon: "trending_up",
    },
    {
      key: "nervousness",
      label: "Nervousness Index",
      value: nervousness,
      caption:
        nervousness <= 30
          ? "Low / Controlled"
          : nervousness <= 60
          ? "Moderate"
          : "Elevated",
      color: "text-amber-400",
      bar: "bg-amber-400",
      ring: "border-amber-500/30 bg-amber-500/10",
      icon: "monitor_heart",
    },
    {
      key: "composure",
      label: "Composure Level",
      value: composure,
      caption: levelLabel(composure, "Shaky", "Composed"),
      color: "text-sky-400",
      bar: "bg-sky-400",
      ring: "border-sky-500/30 bg-sky-500/10",
      icon: "self_improvement",
    },
  ];

  return (
    <section
      className={`relative z-10 rounded-2xl bg-surface-container-low border ${theme.border} p-6 flex flex-col gap-5 shadow-lg print:break-inside-avoid print:border-black/20 print:bg-white`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-xl ${theme.bg} ${theme.border} border flex items-center justify-center`}
          >
            <span className={`material-symbols-outlined text-[22px] ${theme.text}`}>
              graphic_eq
            </span>
          </div>
          <div>
            <h2 className="font-headline-md text-lg font-bold text-on-surface print:text-black">
              Vocal Delivery &amp; Presence
            </h2>
            <p className="text-xs text-on-surface-variant">
              Server-side speech emotion telemetry captured during the session.
            </p>
          </div>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold ${theme.bg} ${theme.border} ${theme.text}`}
        >
          <span className="material-symbols-outlined text-[15px]">mic</span>
          {summary.delivery_style || "Neutral Delivery"}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {metrics.map((metric) => (
          <div
            key={metric.key}
            className={`rounded-xl border ${metric.ring} p-4 flex flex-col gap-2`}
          >
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-[10px] uppercase tracking-wider text-outline font-semibold">
                {metric.label}
              </span>
              <span className={`material-symbols-outlined text-[18px] ${metric.color}`}>
                {metric.icon}
              </span>
            </div>
            <div className="flex items-baseline gap-1">
              <span className={`font-display-hero text-4xl font-black font-label-numeric ${metric.color}`}>
                {metric.value}
              </span>
              <span className="text-xs font-semibold text-outline">/ 100</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
              <div
                className={`h-full rounded-full ${metric.bar}`}
                style={{ width: `${metric.value}%` }}
              />
            </div>
            <span className="text-[11px] text-on-surface-variant font-medium">
              {metric.caption}
            </span>
          </div>
        ))}
      </div>

      {sampledTimeline.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-[10px] uppercase tracking-wider text-outline font-semibold">
              Confidence Timeline
            </span>
            <span className="text-[10px] text-outline">
              {timeline.length} sampled windows
            </span>
          </div>
          <div className="flex items-end gap-1 h-12">
            {sampledTimeline.map((point, index) => {
              const height = Math.max(
                6,
                Math.min(100, point.confidence ?? 0)
              );
              return (
                <div
                  key={index}
                  className={`flex-1 rounded-t-sm ${theme.bar} opacity-80`}
                  style={{ height: `${height}%` }}
                  title={`Confidence ${Math.round(point.confidence ?? 0)}`}
                />
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
