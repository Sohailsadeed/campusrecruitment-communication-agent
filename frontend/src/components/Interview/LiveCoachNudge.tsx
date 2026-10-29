import type { CoachNudge } from "../../hooks/useLiveEmotionStream";

interface LiveCoachNudgeProps {
  nudge: CoachNudge | null;
}

export default function LiveCoachNudge({ nudge }: LiveCoachNudgeProps) {
  const isTier2 = nudge?.tier === 2;
  const visible = Boolean(nudge);

  return (
    <div
      role="status"
      aria-live="polite"
      className={`pointer-events-none fixed bottom-6 left-1/2 z-50 w-[min(92vw,32rem)] -translate-x-1/2 ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
      }`}
      style={{ transition: "all 0.3s ease-out" }}
    >
      <div
        className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 shadow-lg backdrop-blur ${
          isTier2
            ? "border-indigo-300/70 bg-indigo-50/95 text-indigo-900"
            : "border-amber-300/70 bg-amber-50/95 text-amber-900"
        }`}
      >
        <span className="material-symbols-outlined mt-0.5 text-[18px]">
          lightbulb
        </span>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wider opacity-70">
            {isTier2 ? "Socratic Coach" : "Laya Cadence Coach"}
          </p>
          <p className="text-sm font-medium leading-snug">
            {nudge?.message ?? ""}
          </p>
        </div>
      </div>
    </div>
  );
}
