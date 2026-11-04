import { useEffect, useRef, useState } from "react";
import { apiClient } from "../../api/client";
import {
  attemptCleanup,
  describeAudioError,
  fetchProtectedAudio,
  isStaleResponse,
  playbackReleaseSteps,
  runSequential,
  type NamedStep,
  type PlaybackRecord,
} from "../../api/audioBlob";
import type { SentenceAnalysisItem } from "../../api/technical";

interface SentenceAnalysisProps {
  sentences?: SentenceAnalysisItem[];
  audioUrl?: string | null;
}

type ClipPhase = "idle" | "loading" | "ready" | "error";

function formatTimestamp(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

/** A teardown failure is reported, not swallowed: the object URL may still be live. */
function reportTeardownFailures(failures: string[]): void {
  if (failures.length > 0) {
    console.error("SentenceAnalysis: recording teardown failed", failures);
  }
}

export default function SentenceAnalysis({ sentences, audioUrl }: SentenceAnalysisProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const objectUrlRef = useRef<string>("");
  const abortRef = useRef<AbortController | null>(null);
  const clipAttempt = useRef(0);
  const pendingRef = useRef<SentenceAnalysisItem | null>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [clipPhase, setClipPhase] = useState<ClipPhase>("idle");
  const [clipError, setClipError] = useState<string | null>(null);

  // AUTH-E: a media element cannot authenticate, so a replay fetches the clip through apiClient and
  // plays it from an object URL. Tearing the view down, or pointing it at another clip, revokes it.
  // The view starts from "idle" every time the clip changes, and the cleanup touches only
  // resources — no state write from a teardown that may itself be the unmount.
  useEffect(() => {
    setClipPhase("idle");
    setClipError(null);
    return () => {
      if (stopTimerRef.current !== null) {
        window.clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
      }
      releaseClip();
    };
  }, [audioUrl]);

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

    const current = audioRef.current;
    if (current && activeIndex === sentence.index && !current.paused) {
      if (stopTimerRef.current !== null) {
        window.clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
      }
      current.pause();
      setActiveIndex(null);
      return;
    }

    if (clipPhase !== "ready") {
      pendingRef.current = sentence; // the last sentence clicked is the one that plays once loaded
      if (clipPhase !== "loading") void loadClip();
      return;
    }

    startSentence(sentence);
  };

  function ensureElement(): HTMLAudioElement {
    const el = audioRef.current ?? new Audio(); // no source: nothing is fetched until the blob is installed
    audioRef.current = el;
    return el;
  }

  async function loadClip() {
    if (!audioUrl) return;

    const attempt = (clipAttempt.current += 1);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setClipPhase("loading");
    setClipError(null);

    try {
      const blob = await fetchProtectedAudio(apiClient, audioUrl, ctrl.signal);
      // Currency is checked before the object URL exists, so a stale settle installs no resource.
      if (isStaleResponse(attempt, clipAttempt.current, ctrl.signal.aborted)) return;
      const el = ensureElement();
      let objectUrl: string;
      try {
        objectUrl = URL.createObjectURL(blob);
      } catch (err) {
        failWith(`createObjectURL: ${err instanceof Error ? err.message : String(err)}`);
        return;
      }
      objectUrlRef.current = objectUrl; // claim first: the revoking step is the step that owns it
      const outcome = runSequential([
        ["setAttribute", () => el.setAttribute("src", objectUrl)],
        ["load", () => el.load()],
      ]);
      if (!outcome.ok) {
        const reason = `${outcome.step}: ${outcome.message}`;
        releaseClip();
        failWith(reason);
        return;
      }
      setClipPhase("ready");
      const pending = pendingRef.current;
      pendingRef.current = null;
      if (pending) startSentence(pending);
    } catch (err) {
      if (isStaleResponse(attempt, clipAttempt.current, ctrl.signal.aborted)) return;
      failWith(describeAudioError(err));
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
    }
  }

  function startSentence(sentence: SentenceAnalysisItem) {
    const el = audioRef.current;
    if (!el || typeof sentence.start !== "number") return;

    if (stopTimerRef.current !== null) {
      window.clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }

    seekTo(el, sentence.start);
    void el.play().catch(() => setActiveIndex(null));
    setActiveIndex(sentence.index);

    const end = typeof sentence.end === "number" ? sentence.end : sentence.start + 2;
    const durationMs = Math.max(600, (end - sentence.start) * 1000);
    stopTimerRef.current = window.setTimeout(() => {
      el.pause();
      setActiveIndex(null);
    }, durationMs);
  }

  /** Right after load() the duration is still unknown, so a seek can be dropped; re-apply it when
   *  the metadata arrives. */
  function seekTo(el: HTMLAudioElement, start: number) {
    const target = Math.max(0, start);
    if (el.readyState >= HTMLMediaElement.HAVE_METADATA) {
      el.currentTime = target;
      return;
    }
    el.addEventListener("loadedmetadata", () => {
      el.currentTime = target;
    }, { once: true });
  }

  function failWith(reason: string) {
    pendingRef.current = null;
    setActiveIndex(null);
    setClipPhase("error");
    setClipError(reason);
  }

  function releaseClip() {
    clipAttempt.current += 1; // any in-flight settle for this clip becomes stale on the spot
    pendingRef.current = null;
    const ctrl = abortRef.current;
    abortRef.current = null;
    ctrl?.abort();

    const objectUrl = objectUrlRef.current;
    if (!objectUrl) return;
    objectUrlRef.current = "";
    const el = audioRef.current;
    const steps: NamedStep[] = el
      ? playbackReleaseSteps({ el, objectUrl } as PlaybackRecord)
      : [["revokeObjectURL", () => URL.revokeObjectURL(objectUrl)]];
    reportTeardownFailures(attemptCleanup(steps));
  }

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

      {clipPhase === "loading" && (
        <span role="status" className="text-[10px] text-outline">
          Loading recording…
        </span>
      )}
      {clipPhase === "error" && (
        <span role="alert" className="text-[10px] text-error">
          Playback unavailable: {clipError}
        </span>
      )}

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
