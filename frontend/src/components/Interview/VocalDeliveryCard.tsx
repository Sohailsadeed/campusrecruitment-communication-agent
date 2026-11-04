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
  const prosody = vocalDelivery?.prosody;
  const hasVoice = (prosody?.pitch_mean_hz ?? 0) > 0;
  const pitchStd = prosody?.pitch_std_hz ?? 0;
  const semitoneRange = prosody?.dynamic_range_semitones ?? 0;
  const jitter = prosody?.vocal_jitter_percent ?? 0;
  const hnr = prosody?.hnr_db ?? 0;
  const isMonotone = Boolean(prosody?.is_monotone);
  const hasTremor = Boolean(prosody?.vocal_tremor_flag);
  const clarity = prosody?.delivery_clarity || "Clear";

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

      {prosody && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-[10px] uppercase tracking-wider text-outline font-semibold">
              Vocal Dynamics &amp; Control
            </span>
            <span className="text-[10px] text-outline">
              Praat acoustic telemetry
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div
              className={`rounded-xl border p-4 flex flex-col gap-1.5 ${
                isMonotone
                  ? "border-amber-500/30 bg-amber-500/10"
                  : "border-emerald-500/30 bg-emerald-500/10"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] uppercase tracking-wider text-outline font-semibold">
                  Pitch Modulation
                </span>
                <span
                  className={`material-symbols-outlined text-[18px] ${
                    isMonotone ? "text-amber-400" : "text-emerald-400"
                  }`}
                >
                  ssid_chart
                </span>
              </div>
              <div className="flex items-baseline gap-1">
                <span
                  className={`font-label-numeric text-2xl font-bold ${
                    isMonotone ? "text-amber-400" : "text-emerald-400"
                  }`}
                >
                  {pitchStd}
                </span>
                <span className="text-xs font-semibold text-outline">Hz</span>
              </div>
              <span className="text-[11px] text-on-surface-variant font-medium">
                {!hasVoice
                  ? "No voiced audio detected"
                  : isMonotone
                  ? "Monotone Warning"
                  : "Dynamic & Engaging"}
              </span>
              <span className="text-[10px] text-outline">
                Range {semitoneRange} semitones
              </span>
            </div>

            <div
              className={`rounded-xl border p-4 flex flex-col gap-1.5 ${
                hasTremor
                  ? "border-rose-500/30 bg-rose-500/10"
                  : "border-emerald-500/30 bg-emerald-500/10"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] uppercase tracking-wider text-outline font-semibold">
                  Voice Stability
                </span>
                <span
                  className={`material-symbols-outlined text-[18px] ${
                    hasTremor ? "text-rose-400" : "text-emerald-400"
                  }`}
                >
                  waves
                </span>
              </div>
              <div className="flex items-baseline gap-1">
                <span
                  className={`font-label-numeric text-2xl font-bold ${
                    hasTremor ? "text-rose-400" : "text-emerald-400"
                  }`}
                >
                  {jitter}
                </span>
                <span className="text-xs font-semibold text-outline">%</span>
              </div>
              <span className="text-[11px] text-on-surface-variant font-medium">
                {!hasVoice
                  ? "No voiced audio detected"
                  : hasTremor
                  ? "Vocal Cord Tension"
                  : "Controlled Breath"}
              </span>
              <span className="text-[10px] text-outline">Jitter (local)</span>
            </div>

            <div
              className={`rounded-xl border p-4 flex flex-col gap-1.5 ${
                hnr >= 15
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : hnr >= 10
                  ? "border-amber-500/30 bg-amber-500/10"
                  : "border-rose-500/30 bg-rose-500/10"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] uppercase tracking-wider text-outline font-semibold">
                  Clarity
                </span>
                <span
                  className={`material-symbols-outlined text-[18px] ${
                    hnr >= 15
                      ? "text-emerald-400"
                      : hnr >= 10
                      ? "text-amber-400"
                      : "text-rose-400"
                  }`}
                >
                  graphic_eq
                </span>
              </div>
              <div className="flex items-baseline gap-1">
                <span
                  className={`font-label-numeric text-2xl font-bold ${
                    hnr >= 15
                      ? "text-emerald-400"
                      : hnr >= 10
                      ? "text-amber-400"
                      : "text-rose-400"
                  }`}
                >
                  {hnr}
                </span>
                <span className="text-xs font-semibold text-outline">dB</span>
              </div>
              <span className="text-[11px] text-on-surface-variant font-medium">
                {!hasVoice ? "No voiced audio detected" : `${clarity} Articulation`}
              </span>
              <span className="text-[10px] text-outline">
                Harmonics-to-noise ratio
              </span>
            </div>
          </div>
        </div>
      )}

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
