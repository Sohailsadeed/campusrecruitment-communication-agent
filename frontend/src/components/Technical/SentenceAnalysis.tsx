import { useEffect, useRef, useState } from "react";
import type { SentenceAnalysisItem } from "../../api/technical";

interface SentenceAnalysisProps {
  sentences?: SentenceAnalysisItem[];
  audioUrl?: string | null;
}

function formatTimestamp(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export default function SentenceAnalysis({ sentences, audioUrl }: SentenceAnalysisProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  useEffect(() => {
    return () => {
      if (stopTimerRef.current !== null) {
        window.clearTimeout(stopTimerRef.current);
      }
      audioRef.current?.pause();
    };
  }, []);

  if (!sentences || sentences.length === 0) {
    return null;
  }

  const hasCheckpoint = sentences.some((sentence) => sentence.is_conclusion_checkpoint);
  const hasRambling = sentences.some((sentence) => sentence.is_rambling);
  if (!hasCheckpoint && !hasRambling) {
    return null;
  }

  const playSentence = (sentence: SentenceAnalysisItem) => {
    if (!audioUrl || typeof sentence.start !== "number") return;

    if (stopTimerRef.current !== null) {
      window.clearTimeout(stopTimerRef.current);
    }

    let audio = audioRef.current;
    if (!audio) {
      audio = new Audio(audioUrl);
      audioRef.current = audio;
    }

    if (activeIndex === sentence.index && !audio.paused) {
      audio.pause();
      setActiveIndex(null);
      return;
    }

    audio.currentTime = Math.max(0, sentence.start);
    void audio.play().catch(() => setActiveIndex(null));
    setActiveIndex(sentence.index);

    const end = typeof sentence.end === "number" ? sentence.end : sentence.start + 2;
    const durationMs = Math.max(600, (end - sentence.start) * 1000);
    stopTimerRef.current = window.setTimeout(() => {
      audio?.pause();
      setActiveIndex(null);
    }, durationMs);
  };

  return (
    <div className="rounded-lg bg-surface-container-low border border-outline-variant/20 p-3.5 flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-label-caps text-[10px] uppercase text-secondary font-bold flex items-center gap-1">
          <span className="material-symbols-outlined text-[14px]">segment</span>
          Sentence-Level Conclusion Checkpoint
        </span>
        <div className="flex items-center gap-3 text-[10px] font-semibold text-on-surface-variant">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            Core answer
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            Post-checkpoint rambling
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        {sentences.map((sentence) => {
          const isCheckpoint = !!sentence.is_conclusion_checkpoint;
          const isRambling = !!sentence.is_rambling;
          const canReplay =
            !!audioUrl && typeof sentence.start === "number" && sentence.start >= 0;
          const isActive = activeIndex === sentence.index;

          return (
            <div
              key={sentence.index}
              className={[
                "flex items-start gap-2.5 rounded-md border px-2.5 py-2 transition-colors",
                isRambling
                  ? "bg-rose-500/10 border-rose-500/30"
                  : isCheckpoint
                    ? "bg-emerald-500/10 border-emerald-500/30"
                    : "bg-surface-container border-outline-variant/15",
                isActive ? "ring-1 ring-secondary" : "",
              ].join(" ")}
            >
              <span
                className={[
                  "mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[10px] font-bold",
                  isRambling
                    ? "bg-rose-500/20 text-rose-500"
                    : isCheckpoint
                      ? "bg-emerald-500/20 text-emerald-600"
                      : "bg-surface-container-high text-outline",
                ].join(" ")}
              >
                {sentence.index + 1}
              </span>

              <div className="min-w-0 flex-1">
                <p
                  className={[
                    "text-xs leading-relaxed",
                    isRambling
                      ? "text-rose-600 dark:text-rose-300"
                      : "text-on-surface-variant",
                  ].join(" ")}
                >
                  {sentence.text}
                </p>
                {isRambling && sentence.rationale && (
                  <p className="mt-1 text-[10px] font-medium text-rose-500">
                    {sentence.rationale}
                  </p>
                )}
              </div>

              <div className="flex flex-shrink-0 items-center gap-1.5">
                {isCheckpoint && (
                  <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-600">
                    Stop here
                  </span>
                )}
                {isRambling && (
                  <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-rose-500">
                    Rambling
                  </span>
                )}
                {canReplay && (
                  <button
                    type="button"
                    onClick={() => playSentence(sentence)}
                    className="flex items-center gap-1 rounded border border-secondary/30 bg-secondary/10 px-1.5 py-0.5 text-[10px] font-bold text-secondary transition-colors hover:bg-secondary/20"
                    title="Replay this sentence"
                  >
                    <span className="material-symbols-outlined text-[12px]">
                      {isActive ? "pause" : "play_arrow"}
                    </span>
                    {formatTimestamp(sentence.start as number)}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
