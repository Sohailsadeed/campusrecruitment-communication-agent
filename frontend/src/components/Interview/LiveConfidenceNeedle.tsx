import type { LiveEmotionState } from "../../hooks/useLiveEmotionStream";

interface LiveConfidenceNeedleProps {
  emotion: LiveEmotionState | null;
  isRecording?: boolean;
}

interface GaugeBand {
  label: string;
  needle: string;
  dot: string;
  bg: string;
  text: string;
  accent: string;
  from: string;
  to: string;
}

const BANDS: { min: number; band: GaugeBand }[] = [
  {
    min: 70,
    band: {
      label: "High Confidence",
      needle: "stroke-emerald-400",
      dot: "fill-emerald-400",
      bg: "bg-emerald-400",
      text: "text-emerald-400",
      accent: "bg-emerald-500/10 border-emerald-500/30",
      from: "#34d399",
      to: "#10b981",
    },
  },
  {
    min: 40,
    band: {
      label: "Steady & Measured",
      needle: "stroke-amber-400",
      dot: "fill-amber-400",
      bg: "bg-amber-400",
      text: "text-amber-400",
      accent: "bg-amber-500/10 border-amber-500/30",
      from: "#fbbf24",
      to: "#60a5fa",
    },
  },
  {
    min: 0,
    band: {
      label: "Tentative / Hesitant",
      needle: "stroke-rose-400",
      dot: "fill-rose-400",
      bg: "bg-rose-400",
      text: "text-rose-400",
      accent: "bg-rose-500/10 border-rose-500/30",
      from: "#fb7185",
      to: "#f97316",
    },
  },
];

const ARC_LENGTH = Math.PI * 50;

export default function LiveConfidenceNeedle({
  emotion,
  isRecording = false,
}: LiveConfidenceNeedleProps) {
  const hasData = Boolean(emotion);
  const confidence = Math.max(
    0,
    Math.min(100, hasData ? emotion!.confidence : 0)
  );
  const nervousness = Math.max(
    0,
    Math.min(100, hasData ? emotion!.nervousness : 0)
  );
  const composure = Math.max(
    0,
    Math.min(100, hasData ? emotion!.composure : 0)
  );

  const band = BANDS.find((entry) => confidence >= entry.min)!.band;
  const angle = -90 + (confidence / 100) * 180;
  const dashOffset = ARC_LENGTH - (confidence / 100) * ARC_LENGTH;
  const status = hasData
    ? emotion!.delivery_style || band.label
    : isRecording
    ? "Listening..."
    : "Awaiting voice";

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-4 p-4 rounded-xl bg-surface-container border border-outline-variant/30 shadow-sm">
      <div className="relative shrink-0 self-center">
        <svg viewBox="0 0 120 72" className="w-36 h-[76px]">
          <defs>
            <linearGradient id="confidenceGaugeGradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={band.from} />
              <stop offset="100%" stopColor={band.to} />
            </linearGradient>
          </defs>
          <path
            d="M10 60 A50 50 0 0 1 110 60"
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            strokeLinecap="round"
            className="text-surface-container-highest"
          />
          <path
            d="M10 60 A50 50 0 0 1 110 60"
            fill="none"
            stroke="url(#confidenceGaugeGradient)"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={ARC_LENGTH}
            strokeDashoffset={dashOffset}
            style={{ transition: "stroke-dashoffset 0.4s ease-out" }}
          />
          <g
            transform={`rotate(${angle} 60 60)`}
            style={{ transition: "transform 0.4s ease-out" }}
          >
            <line
              x1="60"
              y1="60"
              x2="60"
              y2="24"
              strokeWidth="3.5"
              strokeLinecap="round"
              className={band.needle}
            />
            <circle cx="60" cy="60" r="5.5" className={band.dot} />
          </g>
        </svg>
        <div className="absolute inset-x-0 bottom-0 text-center">
          <span className="font-label-numeric text-2xl font-bold text-on-surface">
            {hasData ? Math.round(confidence) : "--"}
          </span>
          <span className="text-[10px] text-outline ml-0.5">/100</span>
        </div>
      </div>

      <div className="flex-1 min-w-0 flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="font-label-caps text-[11px] uppercase tracking-wider text-outline font-semibold">
            Live Confidence Needle
          </span>
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${band.accent} ${band.text}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${band.bg}`} />
            {status}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="flex items-center justify-between text-[11px] mb-1">
              <span className="text-outline">Nervousness</span>
              <span className="font-label-numeric text-on-surface font-semibold">
                {hasData ? Math.round(nervousness) : "--"}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
              <div
                className="h-full rounded-full bg-rose-400/80"
                style={{
                  width: `${hasData ? nervousness : 0}%`,
                  transition: "width 0.4s ease-out",
                }}
              />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-[11px] mb-1">
              <span className="text-outline">Composure</span>
              <span className="font-label-numeric text-on-surface font-semibold">
                {hasData ? Math.round(composure) : "--"}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
              <div
                className="h-full rounded-full bg-sky-400/80"
                style={{
                  width: `${hasData ? composure : 0}%`,
                  transition: "width 0.4s ease-out",
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
