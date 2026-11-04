import { useEffect, useState } from "react";
import { getHRSpeechTrends } from "../../api/hr";
import type { SpeechRoundBlock, SpeechTrendsResponse } from "../../api/hr";

interface SpeechDeliveryCardProps {
  speech?: SpeechRoundBlock | null;
}

const LABELS: Record<string, string> = {
  words_per_minute: "Speaking rate",
  fillers_per_100_words: "Filler words per 100 words",
  pause_seconds: "Average pause",
  silence_seconds: "Silence per answer",
  answer_words: "Answer length",
};

/** Words a candidate can act on, and only what two rounds both measured. */
function TrendRow({ metric, previous, latest, delta }: {
  metric: string;
  previous: number;
  latest: number;
  delta: number;
}) {
  const lowerIsBetter = metric === "fillers_per_100_words" || metric === "silence_seconds";
  const improved = lowerIsBetter ? delta < 0 : delta > 0;
  return (
    <li className="flex items-baseline justify-between gap-2 text-sm">
      <span className="text-on-surface">{LABELS[metric] ?? metric}</span>
      <span className="text-on-surface-variant font-mono text-xs">
        {previous} → {latest}
        <span className={improved ? "text-emerald-400 ml-2" : "text-rose-400 ml-2"}>
          {delta > 0 ? "+" : ""}
          {delta}
        </span>
      </span>
    </li>
  );
}

/** Figures a transcript can prove, with the words they came from.
 *
 *  A metric the recording could not support reads "Not measured" rather than a plausible number —
 *  a typed answer with no recording has no speaking rate, and showing one would be a fabrication.
 */
function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  const measured = value !== "Not measured";
  return (
    <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low/40 px-3 py-2">
      <p className="font-headline-sm text-[11px] uppercase tracking-wide text-on-surface-variant">
        {label}
      </p>
      <p
        className={
          measured
            ? "font-headline text-lg text-on-surface"
            : "font-headline text-lg text-on-surface-variant/60 italic"
        }
      >
        {value}
      </p>
      {hint && measured && (
        <p className="text-[11px] text-on-surface-variant/80 leading-snug mt-0.5">{hint}</p>
      )}
    </div>
  );
}

const MISSING = "Not measured";

export default function SpeechDeliveryCard({ speech }: SpeechDeliveryCardProps) {
  const [history, setHistory] = useState<SpeechTrendsResponse | null>(null);

  useEffect(() => {
    let alive = true;
    getHRSpeechTrends()
      .then((res) => {
        if (alive) setHistory(res);
      })
      .catch(() => {
        /* a round's own figures stand on their own; the trend is an addition, not a dependency */
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!speech) return null;

  const answers = speech.answers ?? [];
  const averages = speech.averages ?? {};
  const observations = speech.observations ?? [];
  const unusualPauses = answers.reduce((total, a) => total + (a.unusual_pause_count ?? 0), 0);

  return (
    <section className="rounded-2xl border border-secondary/30 bg-secondary/10 p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="font-headline text-xl text-on-surface">How you communicated it</h2>
          <p className="text-xs text-on-surface-variant">
            Measured from your transcript and the word timings of your recording. Silence is
            excluded from pace.
          </p>
        </div>
        {speech.answers_without_speech_data?.length > 0 && (
          <span className="text-[11px] px-2 py-1 rounded-full border border-outline-variant/40 text-on-surface-variant">
            {speech.answers_without_speech_data.length} answer(s) predate speech analytics
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric
          label="Speaking rate"
          value={
            typeof averages.words_per_minute === "number"
              ? `${averages.words_per_minute} wpm`
              : MISSING
          }
          hint="Averaged over the answers that had a recording"
        />
        <Metric
          label="Filler words"
          value={
            typeof averages.fillers_per_100_words === "number"
              ? `${averages.fillers_per_100_words} per 100 words`
              : MISSING
          }
        />
        <Metric
          label="Pauses"
          value={
            typeof averages.pause_seconds === "number"
              ? `${averages.pause_seconds}s avg${unusualPauses ? ` · ${unusualPauses} long` : ""}`
              : MISSING
          }
        />
        <Metric
          label="Answer length"
          value={
            typeof averages.answer_words === "number"
              ? `${averages.answer_words} words`
              : MISSING
          }
        />
      </div>

      {observations.length > 0 ? (
        <ul className="space-y-2">
          {observations.map((observation, index) => (
            <li
              key={`${observation.question_number}-${observation.metric}-${index}`}
              className="rounded-xl border border-outline-variant/30 bg-surface-container-lowest/60 px-3 py-2"
            >
              <p className="text-sm text-on-surface">
                <span className="font-headline-sm text-[11px] uppercase tracking-wide text-secondary mr-2">
                  Q{observation.question_number}
                </span>
                {observation.text}
              </p>
              {observation.excerpt && (
                <p className="text-[11px] text-on-surface-variant mt-1 font-mono break-words">
                  from your transcript: {observation.excerpt}
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-on-surface-variant">
          Nothing in this round crossed the thresholds worth quoting back — no unusually long
          pause, no restated point and no hesitation rate above the reporting bar.
        </p>
      )}

      {history?.compared && (
        <div className="rounded-xl border border-outline-variant/30 bg-surface-container-lowest/60 px-3 py-2">
          <p className="font-headline-sm text-[11px] uppercase tracking-wide text-on-surface-variant">
            Across your {history.compared.rounds_compared} measured rounds
          </p>
          <ul className="mt-1 space-y-1">
            {Object.entries(history.compared.changes).map(([metric, change]) => (
              <TrendRow key={metric} metric={metric} {...change} />
            ))}
          </ul>
          {history.compared.not_compared.length > 0 && (
            <p className="text-[11px] text-on-surface-variant/80 mt-2">
              Not compared — measured in only one of these rounds:{" "}
              {history.compared.not_compared.join(", ")}
            </p>
          )}
        </div>
      )}

      {answers.some((a) => (a.unavailable?.length ?? 0) > 0) && (
        <details className="text-xs text-on-surface-variant">
          <summary className="cursor-pointer font-headline-sm">
            Metrics this round could not measure
          </summary>
          <ul className="mt-2 space-y-1">
            {answers
              .filter((a) => (a.unavailable?.length ?? 0) > 0)
              .map((a) => (
                <li key={a.question_number}>
                  Question {a.question_number}: {a.unavailable.join(", ")}
                </li>
              ))}
          </ul>
        </details>
      )}
    </section>
  );
}
