import { useEffect, useState, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { getHRReport, HRSessionResponse, HRQuestionItem } from "../../api/hr";
import VocalDeliveryCard from "../../components/Interview/VocalDeliveryCard";

export default function HRReport() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<HRSessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeQuestionIndex, setActiveQuestionIndex] = useState(0);
  const [isPlayingTTS, setIsPlayingTTS] = useState(false);
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    getHRReport(Number(sessionId))
      .then((res) => {
        setData(res);
      })
      .catch((err: any) => {
        setError(err?.response?.data?.detail || "Failed to load HR behavioral assessment dossier.");
      })
      .finally(() => {
        setLoading(false);
      });

    return () => {
      window.speechSynthesis.cancel();
    };
  }, [sessionId]);

  const handleExportPDF = () => {
    window.print();
  };

  const toggleTTS = (textToSpeak: string) => {
    if (isPlayingTTS) {
      window.speechSynthesis.cancel();
      setIsPlayingTTS(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.rate = 0.98;
    utterance.pitch = 1.0;
    utterance.onend = () => setIsPlayingTTS(false);
    utterance.onerror = () => setIsPlayingTTS(false);
    speechRef.current = utterance;
    setIsPlayingTTS(true);
    window.speechSynthesis.speak(utterance);
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[70vh] gap-4">
        <div className="w-12 h-12 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <span className="font-headline-sm text-sm text-on-surface-variant font-medium">
          Compiling HR &amp; Behavioral Assessment Dossier...
        </span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh] gap-4 px-4 text-center">
        <div className="w-16 h-16 rounded-2xl bg-error-container/20 border border-error/30 text-error flex items-center justify-center">
          <span className="material-symbols-outlined text-[32px]">warning</span>
        </div>
        <h2 className="font-headline-md text-xl font-bold text-on-surface">Report Unavailable</h2>
        <p className="text-sm text-on-surface-variant max-w-md">{error || "Could not retrieve HR session dossier."}</p>
        <Link
          to="/hr"
          className="px-5 py-2.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-headline-sm text-xs font-semibold transition-colors flex items-center gap-2 mt-2"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          <span>Return to HR Studio</span>
        </Link>
      </div>
    );
  }

  const questions: HRQuestionItem[] = data.questions || [];
  const currentQ: HRQuestionItem | undefined = questions[activeQuestionIndex];
  const evalData = currentQ?.evaluation;
  const reportSummary = data.report;
  const overallScore = data.overall_score || reportSummary?.total_score || 0;

  // Verdict calculation
  let verdict = { text: "Developing Behavioral Presence", color: "text-amber-400 bg-amber-500/10 border-amber-500/20" };
  if (overallScore >= 85) {
    verdict = { text: "Executive & Culture Leader Ready", color: "text-primary bg-primary/10 border-primary/30" };
  } else if (overallScore >= 70) {
    verdict = { text: "Strong STAR Practitioner", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" };
  } else if (overallScore < 50) {
    verdict = { text: "Needs Structural & Ownership Rigor", color: "text-rose-400 bg-rose-500/10 border-rose-500/20" };
  }

  const star = evalData?.star_structure;

  return (
    <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-7xl mx-auto flex flex-col gap-8 print:p-0 print:max-w-none print:text-black">
      {/* Print Stylesheet */}
      <style>{`
        @media print {
          body {
            background: white !important;
            color: #111 !important;
          }
          nav, aside, header, .no-print, audio, button {
            display: none !important;
          }
          .print\\:break-inside-avoid {
            break-inside: avoid !important;
            page-break-inside: avoid !important;
          }
        }
      `}</style>

      {/* Ambient Backdrop Aura */}
      <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-primary/10 rounded-full blur-[140px] print:hidden" />
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary/10 rounded-full blur-[120px] print:hidden" />

      {/* Top Header & Breadcrumbs */}
      <div className="relative z-10 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-outline-variant/30 print:border-b-2 print:border-black/20">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 text-xs text-outline font-label-caps print:hidden">
            <Link to="/" className="hover:text-on-surface transition-colors">Practice Arena</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <Link to="/hr" className="hover:text-on-surface transition-colors">HR Behavioral Studio</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-primary font-semibold">Assessment Dossier</span>
          </div>

          <h1 className="font-display-hero text-2xl sm:text-4xl font-extrabold text-on-surface tracking-tight print:text-black">
            HR &amp; Behavioral Assessment Dossier
          </h1>

          <p className="text-sm text-on-surface-variant flex flex-wrap items-center gap-2 print:text-gray-700">
            <span>Target Role: <strong className="text-on-surface font-semibold print:text-black">{data.role}</strong></span>
            {data.target_company && (
              <>
                <span className="text-outline print:text-gray-400">•</span>
                <span>Company: <strong className="text-primary font-semibold print:text-black">{data.target_company}</strong></span>
              </>
            )}
            <span className="text-outline print:text-gray-400">•</span>
            <span>Mode: <strong className="capitalize">{data.interview_mode.replace("_", " ")}</strong></span>
            {data.created_at && (
              <>
                <span className="text-outline print:text-gray-400">•</span>
                <span>Date: <strong className="font-medium">{new Date(data.created_at).toLocaleDateString()}</strong></span>
              </>
            )}
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-3 print:hidden">
          <button
            type="button"
            onClick={handleExportPDF}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-headline-sm text-xs font-semibold transition-colors border border-outline-variant/30"
          >
            <span className="material-symbols-outlined text-[18px]">download</span>
            <span>Export PDF Dossier</span>
          </button>
          <button
            type="button"
            onClick={() => navigate("/hr")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:opacity-90 text-on-primary font-headline-sm text-xs font-bold transition-all shadow-md shadow-primary/20"
          >
            <span className="material-symbols-outlined text-[18px]">add_circle</span>
            <span>New Behavioral Drill</span>
          </button>
        </div>
      </div>

      <VocalDeliveryCard
        vocalDelivery={reportSummary?.vocal_delivery}
        accent="primary"
      />

      {/* Top Banner: Score & 3 Diagnostic Pillars */}
      <div className="relative z-10 grid grid-cols-1 lg:grid-cols-4 gap-4 print:grid-cols-4">
        {/* Overall Behavioral Score */}
        <div className="relative overflow-hidden rounded-2xl bg-surface-container-low border border-outline-variant/30 p-6 flex flex-col justify-between shadow-xl">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-xs text-outline uppercase font-bold tracking-wider">
              Behavioral Fit
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${verdict.color}`}>
              {verdict.text}
            </span>
          </div>

          <div className="my-4 flex items-baseline gap-2">
            <span className="font-display-hero text-5xl sm:text-6xl font-black text-on-surface font-label-numeric tracking-tight">
              {overallScore}
            </span>
            <span className="text-sm font-semibold text-outline">/ 100</span>
          </div>

          <div className="flex items-center gap-2 text-xs text-on-surface-variant">
            <span className="material-symbols-outlined text-primary text-[18px]">psychology</span>
            <span>Evaluated against tier-1 behavioral standards</span>
          </div>
        </div>

        {/* Pillar 1: STAR Completeness */}
        <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-5 flex flex-col justify-between shadow-md">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-xs text-outline uppercase font-semibold">STAR Completeness</span>
            <span className="material-symbols-outlined text-primary text-[20px]">view_timeline</span>
          </div>
          <div className="my-2">
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-2xl font-bold font-label-numeric text-on-surface">
                {reportSummary?.avg_star_completeness || (star ? star.completeness_score : 0)}%
              </span>
              <span className="text-xs text-outline font-medium">Coverage</span>
            </div>
            <div className="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-700"
                style={{ width: `${reportSummary?.avg_star_completeness || (star ? star.completeness_score : 0)}%` }}
              />
            </div>
          </div>
          <p className="text-[11px] text-on-surface-variant leading-snug">
            Measures if Situation, Task, Action, and Result components are all articulated.
          </p>
        </div>

        {/* Pillar 2: Personal Ownership ("I" vs "We") */}
        <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-5 flex flex-col justify-between shadow-md">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-xs text-outline uppercase font-semibold">Personal Ownership</span>
            <span className="material-symbols-outlined text-secondary text-[20px]">badge</span>
          </div>
          <div className="my-2">
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-2xl font-bold font-label-numeric text-secondary">
                {reportSummary?.avg_ownership_score || (evalData ? evalData.personal_ownership_score : 0)}%
              </span>
              <span className="text-xs text-outline font-medium">&quot;I&quot; Agency</span>
            </div>
            <div className="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden">
              <div
                className="h-full bg-secondary rounded-full transition-all duration-700"
                style={{ width: `${reportSummary?.avg_ownership_score || (evalData ? evalData.personal_ownership_score : 0)}%` }}
              />
            </div>
          </div>
          <p className="text-[11px] text-on-surface-variant leading-snug">
            Flags passive team masking (&quot;we did&quot;). Rewards active individual accountability.
          </p>
        </div>

        {/* Pillar 3: Specificity & Evidence */}
        <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-5 flex flex-col justify-between shadow-md">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-xs text-outline uppercase font-semibold">Evidence &amp; Metrics</span>
            <span className="material-symbols-outlined text-tertiary text-[20px]">insights</span>
          </div>
          <div className="my-2">
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-2xl font-bold font-label-numeric text-tertiary">
                {reportSummary?.avg_specificity_score || (evalData ? evalData.specificity_score : 0)}%
              </span>
              <span className="text-xs text-outline font-medium">Data Rigor</span>
            </div>
            <div className="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden">
              <div
                className="h-full bg-tertiary rounded-full transition-all duration-700"
                style={{ width: `${reportSummary?.avg_specificity_score || (evalData ? evalData.specificity_score : 0)}%` }}
              />
            </div>
          </div>
          <p className="text-[11px] text-on-surface-variant leading-snug">
            Differentiates vague hand-waving from quantifiable business outcomes.
          </p>
        </div>
      </div>

      {/* Multi-Question Selector Tabs (if more than 1 question) */}
      {questions.length > 1 && (
        <div className="relative z-10 flex items-center gap-2 overflow-x-auto pb-2 print:hidden">
          <span className="font-label-caps text-xs text-outline uppercase font-semibold mr-2">Questions:</span>
          {questions.map((q, idx) => (
            <button
              key={q.id || idx}
              type="button"
              onClick={() => setActiveQuestionIndex(idx)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                idx === activeQuestionIndex
                  ? "bg-primary text-on-primary shadow-md shadow-primary/20"
                  : "bg-surface-container hover:bg-surface-container-high text-on-surface-variant"
              }`}
            >
              <span>Q{idx + 1}</span>
              <span className="opacity-75 font-normal">({q.track.replace("_", " ")})</span>
              {q.evaluation && (
                <span className="ml-1 text-[11px] px-1.5 py-0.2 rounded bg-black/20 font-bold">
                  {q.evaluation.overall_score}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Active Question & Candidate Answer Section */}
      {currentQ && (
        <div className="relative z-10 flex flex-col gap-6">
          {/* Question Prompt Card */}
          <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-6 flex flex-col gap-4 shadow-lg print:break-inside-avoid">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="px-3 py-1 rounded-md bg-primary/10 border border-primary/20 text-primary text-xs font-bold uppercase tracking-wider">
                  Q{activeQuestionIndex + 1} &middot; {currentQ.track.replace("_", " ")}
                </span>
                {currentQ.evaluation && (
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-surface-container-high text-on-surface font-label-numeric">
                    Score: {currentQ.evaluation.overall_score}/100
                  </span>
                )}
              </div>

              {/* Spoken Audio Player */}
              {currentQ.audio_url && (
                <div className="flex items-center gap-2 bg-surface-container-high px-3 py-1.5 rounded-lg border border-outline-variant/30 print:hidden">
                  <span className="material-symbols-outlined text-[18px] text-secondary">mic</span>
                  <span className="text-xs font-medium text-on-surface">Your Articulation:</span>
                  <audio controls src={currentQ.audio_url} className="h-7 w-48 sm:w-56" />
                </div>
              )}
            </div>

            <h2 className="text-lg sm:text-xl font-bold text-on-surface leading-relaxed">
              &ldquo;{currentQ.text}&rdquo;
            </h2>

            {/* Candidate Spoken Response Transcript */}
            <div className="rounded-xl bg-surface-container-lowest p-4 border border-outline-variant/20 flex flex-col gap-2">
              <span className="font-label-caps text-[11px] text-outline uppercase font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[15px] text-primary">record_voice_over</span>
                Verbatim Candidate Response Transcript
              </span>
              <p className="text-sm text-on-surface-variant font-mono whitespace-pre-wrap leading-relaxed">
                {currentQ.answer || "No response text captured."}
              </p>
            </div>
          </div>

          {/* STAR Method Quadrant Breakdown */}
          {star && (
            <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-6 flex flex-col gap-5 shadow-lg print:break-inside-avoid">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-outline-variant/20 pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[20px]">view_timeline</span>
                  </div>
                  <div>
                    <h3 className="font-headline-sm text-base font-bold text-on-surface">
                      STAR Narrative Decomposition
                    </h3>
                    <p className="text-xs text-outline">
                      Rigorous structural analysis of your behavioral narrative
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-on-surface-variant">Completeness Score:</span>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-primary/15 text-primary border border-primary/30 font-label-numeric">
                    {star.completeness_score}%
                  </span>
                </div>
              </div>

              {/* 4 Quadrants: S - T - A - R */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Situation */}
                <div
                  className={`rounded-xl p-4 border flex flex-col justify-between transition-all ${
                    star.situation.present
                      ? "bg-surface-container border-emerald-500/30"
                      : "bg-surface-container/50 border-rose-500/30"
                  }`}
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <span className="font-headline-sm text-xs font-black uppercase tracking-wider text-primary">
                        [S] Situation
                      </span>
                      {star.situation.present ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400">
                          <span className="material-symbols-outlined text-[14px]">check_circle</span>
                          Detected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-400">
                          <span className="material-symbols-outlined text-[14px]">cancel</span>
                          Missing
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-on-surface-variant leading-relaxed">
                      {star.situation.summary}
                    </p>
                  </div>
                </div>

                {/* Task */}
                <div
                  className={`rounded-xl p-4 border flex flex-col justify-between transition-all ${
                    star.task.present
                      ? "bg-surface-container border-emerald-500/30"
                      : "bg-surface-container/50 border-rose-500/30"
                  }`}
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <span className="font-headline-sm text-xs font-black uppercase tracking-wider text-secondary">
                        [T] Task
                      </span>
                      {star.task.present ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400">
                          <span className="material-symbols-outlined text-[14px]">check_circle</span>
                          Detected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-400">
                          <span className="material-symbols-outlined text-[14px]">cancel</span>
                          Missing
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-on-surface-variant leading-relaxed">
                      {star.task.summary}
                    </p>
                  </div>
                </div>

                {/* Action */}
                <div
                  className={`rounded-xl p-4 border flex flex-col justify-between transition-all ${
                    star.action.present
                      ? "bg-surface-container border-emerald-500/30"
                      : "bg-surface-container/50 border-rose-500/30"
                  }`}
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <span className="font-headline-sm text-xs font-black uppercase tracking-wider text-tertiary">
                        [A] Action
                      </span>
                      {star.action.present ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400">
                          <span className="material-symbols-outlined text-[14px]">check_circle</span>
                          Detected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-400">
                          <span className="material-symbols-outlined text-[14px]">cancel</span>
                          Missing
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-on-surface-variant leading-relaxed">
                      {star.action.summary}
                    </p>
                  </div>
                </div>

                {/* Result */}
                <div
                  className={`rounded-xl p-4 border flex flex-col justify-between transition-all ${
                    star.result.present
                      ? "bg-surface-container border-emerald-500/30"
                      : "bg-surface-container/50 border-rose-500/30"
                  }`}
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <span className="font-headline-sm text-xs font-black uppercase tracking-wider text-amber-400">
                        [R] Result
                      </span>
                      {star.result.present ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400">
                          <span className="material-symbols-outlined text-[14px]">check_circle</span>
                          Detected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-400">
                          <span className="material-symbols-outlined text-[14px]">cancel</span>
                          Missing
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-on-surface-variant leading-relaxed">
                      {star.result.summary}
                    </p>
                  </div>
                </div>
              </div>

              {/* Structure Critique */}
              {star.structure_critique && (
                <div className="rounded-xl bg-surface-container p-4 border border-outline-variant/20 flex items-start gap-3">
                  <span className="material-symbols-outlined text-primary text-[20px] shrink-0 mt-0.5">info</span>
                  <div className="flex flex-col gap-1">
                    <span className="font-label-caps text-[11px] text-outline uppercase font-semibold">
                      STAR Structural Feedback
                    </span>
                    <p className="text-xs text-on-surface leading-relaxed">
                      {star.structure_critique}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Deep-Dive Diagnostics: Ownership, Specificity, Relevance */}
          {evalData && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 print:break-inside-avoid">
              {/* Ownership & Agency Critique */}
              <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-5 flex flex-col justify-between shadow-md">
                <div className="flex flex-col gap-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-headline-sm text-xs font-bold text-secondary uppercase tracking-wider flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px]">badge</span>
                      Personal Ownership
                    </span>
                    <span className="font-label-numeric text-sm font-bold text-secondary">
                      {evalData.personal_ownership_score}%
                    </span>
                  </div>
                  <p className="text-xs text-on-surface-variant leading-relaxed">
                    {evalData.ownership_critique}
                  </p>
                </div>
                <div className="mt-3 pt-3 border-t border-outline-variant/20 text-[10px] text-outline">
                  Focus: Explicit &quot;I&quot; actions, personal ownership of setbacks, decision rationale.
                </div>
              </div>

              {/* Specificity Critique */}
              <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-5 flex flex-col justify-between shadow-md">
                <div className="flex flex-col gap-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-headline-sm text-xs font-bold text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px]">insights</span>
                      Concrete Specificity
                    </span>
                    <span className="font-label-numeric text-sm font-bold text-tertiary">
                      {evalData.specificity_score}%
                    </span>
                  </div>
                  <p className="text-xs text-on-surface-variant leading-relaxed">
                    {evalData.specificity_critique}
                  </p>
                </div>
                <div className="mt-3 pt-3 border-t border-outline-variant/20 text-[10px] text-outline">
                  Focus: Quantified business impact, team sizes, deadlines, and metric improvements.
                </div>
              </div>

              {/* Relevance & Fit Critique */}
              <div className="rounded-2xl bg-surface-container-low border border-outline-variant/30 p-5 flex flex-col justify-between shadow-md">
                <div className="flex flex-col gap-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-headline-sm text-xs font-bold text-primary uppercase tracking-wider flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px]">verified_user</span>
                      Relevance &amp; Fit
                    </span>
                    <span className="font-label-numeric text-sm font-bold text-primary">
                      {evalData.relevance_score}%
                    </span>
                  </div>
                  <p className="text-xs text-on-surface-variant leading-relaxed">
                    {evalData.relevance_critique}
                  </p>
                </div>
                <div className="mt-3 pt-3 border-t border-outline-variant/20 text-[10px] text-outline">
                  Focus: Addressing core question intent and culture-fit expectations.
                </div>
              </div>
            </div>
          )}

          {/* Ideal STAR Model Script with Text-to-Speech Playback */}
          {evalData?.ideal_star_script && (
            <div className="rounded-2xl bg-gradient-to-br from-primary/10 via-surface-container-low to-secondary/10 border border-primary/30 p-6 flex flex-col gap-4 shadow-xl print:break-inside-avoid">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-primary/20 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[20px]">record_voice_over</span>
                  </div>
                  <div>
                    <h3 className="font-headline-sm text-base font-bold text-on-surface">
                      Benchmark STAR Articulation Script
                    </h3>
                    <p className="text-xs text-outline">
                      Illustrative benchmark response — serves as an articulation model rather than a singular ideal answer
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => toggleTTS(evalData.ideal_star_script)}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all shadow-sm print:hidden ${
                    isPlayingTTS
                      ? "bg-error text-on-error"
                      : "bg-primary text-on-primary hover:opacity-90"
                  }`}
                >
                  <span className="material-symbols-outlined text-[18px]">
                    {isPlayingTTS ? "stop_circle" : "volume_up"}
                  </span>
                  <span>{isPlayingTTS ? "Stop Audio" : "Listen to Ideal Delivery"}</span>
                </button>
              </div>

              <div className="p-4 rounded-xl bg-surface-container-lowest/80 border border-outline-variant/30">
                <p className="text-sm text-on-surface leading-relaxed font-sans italic">
                  &ldquo;{evalData.ideal_star_script}&rdquo;
                </p>
              </div>

              {evalData.coaching_feedback && (
                <div className="flex items-start gap-2.5 text-xs text-on-surface-variant">
                  <span className="material-symbols-outlined text-secondary text-[18px] shrink-0 mt-0.5">tips_and_updates</span>
                  <div>
                    <strong className="text-secondary font-semibold">Executive Coach Note: </strong>
                    <span>{evalData.coaching_feedback}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Aggregate Behavioral Dossier Summary (Strengths & Growth Areas) */}
      {reportSummary && (
        <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 gap-6 print:break-inside-avoid">
          {/* Strengths */}
          <div className="rounded-2xl bg-surface-container-low border border-emerald-500/30 p-6 flex flex-col gap-4 shadow-lg">
            <div className="flex items-center gap-2.5 text-emerald-400">
              <span className="material-symbols-outlined text-[22px]">thumb_up</span>
              <h3 className="font-headline-sm text-base font-bold">Key Behavioral Strengths</h3>
            </div>
            <ul className="flex flex-col gap-2.5">
              {reportSummary.strengths.map((str, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-on-surface-variant">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 mt-1.5" />
                  <span className="leading-relaxed">{str}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Growth Areas */}
          <div className="rounded-2xl bg-surface-container-low border border-amber-500/30 p-6 flex flex-col gap-4 shadow-lg">
            <div className="flex items-center gap-2.5 text-amber-400">
              <span className="material-symbols-outlined text-[22px]">trending_up</span>
              <h3 className="font-headline-sm text-base font-bold">Strategic Growth Priorities</h3>
            </div>
            <ul className="flex flex-col gap-2.5">
              {reportSummary.weaknesses.map((wk, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-on-surface-variant">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 mt-1.5" />
                  <span className="leading-relaxed">{wk}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Executive Summary Statement */}
      {reportSummary?.executive_summary && (
        <div className="relative z-10 rounded-2xl bg-surface-container-low border border-outline-variant/30 p-6 flex flex-col gap-2 shadow-md print:break-inside-avoid">
          <span className="font-label-caps text-xs text-outline uppercase font-bold tracking-wider">
            Placement Evaluation Executive Summary
          </span>
          <p className="text-sm text-on-surface leading-relaxed">
            {reportSummary.executive_summary}
          </p>
        </div>
      )}

      {/* Bottom Footer Actions */}
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-4 pt-6 border-t border-outline-variant/20 print:hidden">
        <Link
          to="/hr"
          className="px-4 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-semibold flex items-center gap-2 transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">arrow_back</span>
          <span>Back to HR Studio</span>
        </Link>

        <div className="flex items-center gap-3">
          <Link
            to="/dashboard"
            className="px-4 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-semibold flex items-center gap-2 transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">insights</span>
            <span>View All Tracks Dashboard</span>
          </Link>

          <button
            type="button"
            onClick={handleExportPDF}
            className="px-4 py-2 rounded-lg bg-primary hover:opacity-90 text-on-primary text-xs font-bold flex items-center gap-2 transition-all shadow-md shadow-primary/20"
          >
            <span className="material-symbols-outlined text-[16px]">download</span>
            <span>Export Dossier (PDF)</span>
          </button>
        </div>
      </div>
    </div>
  );
}
