import type { HRAnswerEvaluation, HRReportSummary } from "../../api/hr";

/** What the backend recorded about how a score was produced. */
export type EvaluationBasis = NonNullable<HRAnswerEvaluation["evaluator_basis"]>;
export type ReportBasis = NonNullable<HRReportSummary["report_basis"]>;

/** Exception text as the backend stored it, reduced to something safe to put on screen.
 *
 *  The backend already truncates the message, but a library exception can still quote a request URL
 *  with a key in it or a server path. A candidate has no reason to see either, so only an exception
 *  name and a short message survive. The result is rendered as a React child, so markup is
 *  escaped; the remaining risk this guard addresses is disclosure.
 */
export function displayableError(error?: string | null): string | null {
  if (!error) return null;
  let text = error.replace(/\s+/g, " ").trim();
  for (const secret of [/\b(?:sk|pk|key|token|api[-_]?key)[-_][A-Za-z0-9._-]+/gi,
                        /\bBearer\s+[A-Za-z0-9._-]+/gi]) {
    text = text.replace(secret, "[credential removed]");
  }
  text = text.replace(/[A-Za-z]:\\[^\s,;]+|\/(?:home|usr|var|Users|opt)\/[^\s,;]+/g, "[path removed]");
  return text.length > 160 ? `${text.slice(0, 160)}…` : text;
}

const ANSWER_COPY: Record<EvaluationBasis, { label: string; detail: string; tone: string; icon: string }> = {
  model: {
    label: "Model-scored",
    detail: "A language model read this answer and produced the scores below.",
    tone: "border-emerald-500/30 text-emerald-400",
    icon: "workspace_premium",
  },
  fallback: {
    label: "Not model-scored",
    detail: "The model did not return a usable evaluation for this answer, so the scores, STAR "
      + "breakdown and feedback below are SpeakFlow's standard placeholder set — they are not "
      + "measures of what you said.",
    tone: "border-rose-500/40 text-rose-400",
    icon: "science_off",
  },
  heuristic: {
    label: "Not model-scored",
    detail: "This answer was too short to send for model evaluation, so the figures below are a "
      + "fixed floor score rather than an assessment of the content.",
    tone: "border-amber-500/40 text-amber-400",
    icon: "text_snippet",
  },
};

/** One answer's basis, beside its score. */
export function AnswerProvenanceChip({ evaluation }: { evaluation?: HRAnswerEvaluation }) {
  // A stored answer from before this field existed: say nothing rather than claim a model read it.
  if (!evaluation || !evaluation.evaluator_basis) return null;

  const copy = ANSWER_COPY[evaluation.evaluator_basis] ?? ANSWER_COPY.fallback;
  const cause = displayableError(evaluation.evaluator_error);
  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[11px] leading-relaxed print:break-inside-avoid ${copy.tone}`}
      title={copy.detail}
    >
      <span className="material-symbols-outlined text-[15px] shrink-0 mt-px">{copy.icon}</span>
      <div className="flex flex-col gap-0.5">
        <span className="font-label-caps uppercase font-bold tracking-wider">{copy.label}</span>
        <span className="text-on-surface-variant">{copy.detail}</span>
        {cause && (
          <span className="text-on-surface-variant/80 font-mono text-[10px]">
            Reason: {cause}
          </span>
        )}
      </div>
    </div>
  );
}

const REPORT_COPY: Record<ReportBasis, { label: string; detail: string; tone: string; icon: string }> = {
  model: {
    label: "Summary written from your answers",
    detail: "A language model read this round's answers and wrote the strengths, growth areas and "
      + "summary below.",
    tone: "border-emerald-500/30 text-emerald-400",
    icon: "workspace_premium",
  },
  empirical: {
    label: "Summary is arithmetic only",
    detail: "No model wrote the narrative for this round. The averages are computed from the scores "
      + "on record and the strengths, growth areas and summary are SpeakFlow's standard wording.",
    tone: "border-amber-500/40 text-amber-400",
    icon: "calculate",
  },
  heuristic: {
    label: "Summary is a placeholder",
    detail: "This round produced no model evaluation to summarise, so the narrative below is "
      + "SpeakFlow's standard placeholder text.",
    tone: "border-rose-500/40 text-rose-400",
    icon: "science_off",
  },
};

/** Whether the round's narrative came from a model, from arithmetic, or from neither.
 *
 *  A report can look finished while every number in it came from a fixed template. That changes how
 *  much of the dossier a candidate can act on, so it is stated rather than left to be guessed.
 *
 *  `report_basis` undefined means an older report or a backend that predates the field: that is its
 *  own state, because "not recorded" and "a template wrote this" are different facts.
 */
export function ReportProvenanceStrip({ report }: { report?: HRReportSummary | null }) {
  if (!report) return null;

  const basis = report.report_basis;
  const unmodelled = report.answers_not_model_scored ?? 0;

  if (basis === undefined) {
    return (
      <div className="rounded-2xl border border-outline-variant/30 bg-surface-container-low/40 px-4 py-2.5 flex items-start gap-2 text-[11px] print:break-inside-avoid">
        <span className="material-symbols-outlined text-[15px] text-outline shrink-0 mt-px">help</span>
        <p className="text-on-surface-variant leading-relaxed">
          <span className="font-label-caps uppercase font-bold tracking-wider text-outline">
            Provenance not recorded
          </span>{" "}
          — this report predates the backend tracking how it was scored. Every score and comment
          below is reproduced exactly as stored; nothing here has been inferred.
        </p>
      </div>
    );
  }

  const copy = REPORT_COPY[basis] ?? REPORT_COPY.heuristic;
  const cause = displayableError(report.report_error);
  return (
    <div className={`rounded-2xl border bg-surface-container-low/40 px-4 py-2.5 flex flex-wrap items-start gap-x-3 gap-y-1 text-[11px] print:break-inside-avoid ${copy.tone}`}>
      <span className="material-symbols-outlined text-[16px] shrink-0 mt-px">{copy.icon}</span>
      <p className="text-on-surface-variant leading-relaxed flex-1 min-w-[240px]">
        <span className="font-label-caps uppercase font-bold tracking-wider">{copy.label}</span>
        {" — "}
        {copy.detail}
        {unmodelled > 0 && (
          <> {unmodelled} of this round&apos;s answers {unmodelled === 1 ? "was" : "were"} not read by
          a model; each one is marked on its own page.</>
        )}
      </p>
      {cause && (
        <span className="font-mono text-[10px] text-on-surface-variant/80 basis-full">
          Reason: {cause}
        </span>
      )}
    </div>
  );
}
