import { useEffect, useState, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { getTechnicalReport, TechnicalReportResponse } from "../../api/technical";

export default function TechnicalReport() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [reportData, setReportData] = useState<TechnicalReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPlayingTTS, setIsPlayingTTS] = useState(false);
  const [expandedQuestions, setExpandedQuestions] = useState<Record<number, boolean>>({});
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    const fetchReport = async () => {
      try {
        setLoading(true);
        const data = await getTechnicalReport(Number(sessionId));
        setReportData(data);
        // Expand all questions by default so candidate immediately sees articulations and AI feedbacks
        if (data?.questions) {
          const openMap: Record<number, boolean> = {};
          data.questions.forEach((_, idx) => {
            openMap[idx] = true;
          });
          setExpandedQuestions(openMap);
        }
      } catch (err: any) {
        setError(err?.response?.data?.detail || "Failed to load technical interview report.");
      } finally {
        setLoading(false);
      }
    };
    fetchReport();

    return () => {
      window.speechSynthesis.cancel();
    };
  }, [sessionId]);

  const toggleTTS = (textToSpeak: string) => {
    if (isPlayingTTS) {
      window.speechSynthesis.cancel();
      setIsPlayingTTS(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.rate = 1.0;
    utterance.pitch = 0.95;
    utterance.onend = () => setIsPlayingTTS(false);
    utterance.onerror = () => setIsPlayingTTS(false);
    speechRef.current = utterance;
    setIsPlayingTTS(true);
    window.speechSynthesis.speak(utterance);
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[70vh] gap-4">
        <div className="w-12 h-12 rounded-full border-2 border-secondary border-t-transparent animate-spin" />
        <span className="font-headline-sm text-sm text-on-surface-variant font-medium">
          Compiling Technical Evaluation Dossier...
        </span>
      </div>
    );
  }

  if (error || !reportData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh] gap-4 px-4 text-center">
        <div className="w-16 h-16 rounded-2xl bg-error-container/20 border border-error/30 text-error flex items-center justify-center">
          <span className="material-symbols-outlined text-[32px]">warning</span>
        </div>
        <h2 className="font-headline-md text-xl font-bold text-on-surface">Report Unavailable</h2>
        <p className="text-sm text-on-surface-variant max-w-md">{error || "Could not retrieve session dossier."}</p>
        <Link
          to="/technical"
          className="px-5 py-2.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-headline-sm text-xs font-semibold transition-colors flex items-center gap-2 mt-2"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          <span>Return to Studio</span>
        </Link>
      </div>
    );
  }

  const score = reportData.overall_score || reportData.report?.total_score || 0;
  const questions = reportData.questions || [];
  const strengths = reportData.report?.strengths || [];
  const weaknesses = reportData.report?.weaknesses || [];
  const summary = reportData.report?.summary || "Technical session completed.";

  // Verdict calculation
  let verdict = { text: "Needs Focus", color: "text-rose-400 bg-rose-500/10 border-rose-500/20" };
  if (score >= 85) {
    verdict = { text: "Strong Hire", color: "text-tertiary bg-tertiary/10 border-tertiary/30" };
  } else if (score >= 70) {
    verdict = { text: "Competitive Hire", color: "text-secondary bg-secondary/10 border-secondary/30" };
  } else if (score >= 55) {
    verdict = { text: "Lean Hire", color: "text-amber-400 bg-amber-500/10 border-amber-500/20" };
  }

  return (
    <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-7xl mx-auto flex flex-col gap-8">
      {/* Ambient Backdrop Aura */}
      <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-primary/10 rounded-full blur-[140px]" />
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary-container/10 rounded-full blur-[120px]" />

      {/* Top Editorial Breadcrumbs & Header */}
      <div className="relative z-10 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-outline-variant/30">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 text-xs text-outline font-label-caps">
            <Link to="/" className="hover:text-on-surface transition-colors">Practice Arena</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <Link to="/technical" className="hover:text-on-surface transition-colors">Technical Studio</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-secondary font-semibold">Evaluation Dossier</span>
          </div>
          <h1 className="font-display-hero text-2xl sm:text-4xl font-extrabold text-on-surface tracking-tight">
            Technical Assessment Report
          </h1>
          <p className="text-sm text-on-surface-variant flex items-center gap-2">
            <span>Role: <strong className="text-on-surface font-semibold">{reportData.role}</strong></span>
            {reportData.target_company && (
              <>
                <span className="text-outline">•</span>
                <span>Target: <strong className="text-secondary font-semibold">{reportData.target_company}</strong></span>
              </>
            )}
          </p>
        </div>

        {/* Action CTAs */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => toggleTTS(summary)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-headline-sm text-xs font-semibold transition-colors border border-outline-variant/30"
          >
            <span className="material-symbols-outlined text-[18px] text-secondary">
              {isPlayingTTS ? "volume_off" : "volume_up"}
            </span>
            <span>{isPlayingTTS ? "Stop Audio" : "Voice Summary"}</span>
          </button>

          <button
            type="button"
            onClick={() => navigate("/technical")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-secondary text-on-secondary font-headline-sm text-xs font-bold hover:bg-secondary/90 transition-all shadow-md shadow-secondary/20"
          >
            <span className="material-symbols-outlined text-[18px]">replay</span>
            <span>New Drill</span>
          </button>
        </div>
      </div>

      {/* Hero Bento Cards Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 relative z-10">
        {/* Score Card */}
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between shadow-xl">
          <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Overall Technical Score</span>
          <div className="flex items-baseline gap-2 my-2">
            <span className="font-display-hero text-4xl sm:text-5xl font-extrabold text-on-surface font-label-numeric">
              {Math.round(score)}
            </span>
            <span className="text-sm text-outline font-medium">/ 100</span>
          </div>
          <div className="w-full bg-surface-container-highest h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-secondary h-full rounded-full transition-all duration-700"
              style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
            />
          </div>
        </div>

        {/* Evaluator Verdict */}
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between shadow-xl">
          <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Engineering Verdict</span>
          <div className="my-2">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${verdict.color}`}>
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              {verdict.text}
            </span>
          </div>
          <span className="text-xs text-outline font-body-md">Calibrated against tier-1 engineering bar</span>
        </div>

        {/* Questions Completed */}
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between shadow-xl">
          <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Questions Evaluated</span>
          <div className="flex items-baseline gap-2 my-2">
            <span className="font-display-hero text-4xl sm:text-5xl font-extrabold text-on-surface font-label-numeric">
              {questions.length}
            </span>
            <span className="text-sm text-outline font-medium">stages</span>
          </div>
          <span className="text-xs text-outline font-body-md">Adaptive system design & architecture</span>
        </div>

        {/* AI Evaluator Engine */}
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between shadow-xl">
          <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Evaluation Engine</span>
          <div className="my-2 flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary text-[24px]">neurology</span>
            <span className="font-headline-sm text-sm font-bold text-on-surface">Nemotron 550B</span>
          </div>
          <span className="text-[11px] text-tertiary flex items-center gap-1 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-tertiary" />
            RAG Semantic Context Grounded
          </span>
        </div>
      </div>

      {/* Executive Summary Card */}
      <div className="relative z-10 p-6 sm:p-7 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="font-label-caps text-xs uppercase text-secondary font-bold tracking-wider flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">summarize</span>
            Evaluator Executive Synthesis
          </span>
          <span className="text-xs text-outline font-label-numeric-sm">LangGraph Dynamic Report</span>
        </div>
        <p className="text-sm text-on-surface leading-relaxed font-body-md whitespace-pre-line">
          {summary}
        </p>
      </div>

      {/* Strengths & Weaknesses Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 relative z-10">
        {/* Strengths Bento */}
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl flex flex-col gap-4">
          <div className="flex items-center gap-2 text-tertiary font-headline-sm text-sm font-bold">
            <span className="material-symbols-outlined text-[20px]">check_circle</span>
            <span>Demonstrated Strengths</span>
          </div>
          <ul className="flex flex-col gap-2.5">
            {strengths.length > 0 ? (
              strengths.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-on-surface-variant leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-tertiary mt-1.5 flex-shrink-0" />
                  <span>{item}</span>
                </li>
              ))
            ) : (
              <li className="text-xs text-outline">No specific strengths isolated.</li>
            )}
          </ul>
        </div>

        {/* Growth Areas Bento */}
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl flex flex-col gap-4">
          <div className="flex items-center gap-2 text-rose-400 font-headline-sm text-sm font-bold">
            <span className="material-symbols-outlined text-[20px]">troubleshoot</span>
            <span>Architectural Gaps & Growth Areas</span>
          </div>
          <ul className="flex flex-col gap-2.5">
            {weaknesses.length > 0 ? (
              weaknesses.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-on-surface-variant leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-400 mt-1.5 flex-shrink-0" />
                  <span>{item}</span>
                </li>
              ))
            ) : (
              <li className="text-xs text-outline">No critical deficiencies flagged.</li>
            )}
          </ul>
        </div>
      </div>

      {/* Question-by-Question Deep Dive Accordion */}
      <div className="relative z-10 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="font-headline-md text-lg sm:text-xl font-bold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary text-[22px]">list_alt</span>
            <span>Question Breakdown & Telemetry</span>
          </h2>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                const areAllOpen = questions.every((_, idx) => expandedQuestions[idx]);
                const nextState: Record<number, boolean> = {};
                questions.forEach((_, idx) => {
                  nextState[idx] = !areAllOpen;
                });
                setExpandedQuestions(nextState);
              }}
              className="text-xs text-primary hover:text-primary-fixed-dim font-medium transition-colors cursor-pointer flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-[16px]">
                {questions.every((_, idx) => expandedQuestions[idx]) ? "unfold_less" : "unfold_more"}
              </span>
              <span>{questions.every((_, idx) => expandedQuestions[idx]) ? "Collapse All" : "Expand All"}</span>
            </button>
            <span className="text-xs text-outline font-label-numeric-sm">{questions.length} Questions</span>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          {questions.map((q, idx) => {
            const isExpanded = !!expandedQuestions[idx];
            const qScore = q.score !== undefined ? q.score : 0;
            return (
              <div
                key={q.id || idx}
                className="rounded-xl bg-surface-container-low border border-outline-variant/30 overflow-hidden transition-all shadow-md"
              >
                {/* Accordion Header */}
                <button
                  type="button"
                  onClick={() =>
                    setExpandedQuestions((prev) => ({
                      ...prev,
                      [idx]: !prev[idx],
                    }))
                  }
                  className="w-full p-4 sm:p-5 flex items-center justify-between gap-4 text-left hover:bg-surface-container transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="w-7 h-7 rounded-lg bg-surface-container-high text-secondary flex items-center justify-center font-label-numeric-sm text-xs font-bold flex-shrink-0">
                      {idx + 1}
                    </span>
                    <div className="flex flex-col min-w-0">
                      <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">
                        {q.type || "Challenge"}
                      </span>
                      <span className="font-headline-sm text-xs sm:text-sm text-on-surface font-semibold truncate">
                        {q.text}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className="font-label-numeric text-xs font-bold px-2.5 py-1 rounded-md bg-surface-container-high text-on-surface">
                      {qScore} / 10
                    </span>
                    <span className="material-symbols-outlined text-[20px] text-outline transition-transform duration-200">
                      {isExpanded ? "expand_less" : "expand_more"}
                    </span>
                  </div>
                </button>

                {/* Accordion Body */}
                {isExpanded && (
                  <div className="px-5 pb-5 pt-2 border-t border-outline-variant/20 flex flex-col gap-4 bg-surface-container/30">
                    <div>
                      <span className="font-label-caps text-[10px] uppercase text-secondary font-bold flex items-center gap-1 mb-1">
                        <span className="material-symbols-outlined text-[14px]">help_outline</span>
                        Interview Challenge
                      </span>
                      <p className="text-xs sm:text-sm text-on-surface leading-relaxed font-body-md bg-surface-container-low p-3.5 rounded-lg border border-outline-variant/20">
                        {q.text}
                      </p>
                    </div>

                    {q.answer ? (
                      <div>
                        <span className="font-label-caps text-[10px] uppercase text-outline font-semibold flex items-center gap-1 mb-1">
                          <span className="material-symbols-outlined text-[14px]">record_voice_over</span>
                          Candidate Articulation
                        </span>
                        <p className="text-xs sm:text-sm text-on-surface-variant leading-relaxed font-body-md bg-surface-container-low p-3.5 rounded-lg border border-outline-variant/20 whitespace-pre-line">
                          {q.answer}
                        </p>
                      </div>
                    ) : (
                      <div className="text-xs text-outline italic">No spoken articulation recorded for this question.</div>
                    )}

                    {q.feedback && (
                      <div>
                        <span className="font-label-caps text-[10px] uppercase text-tertiary font-bold flex items-center gap-1 mb-1">
                          <span className="material-symbols-outlined text-[14px]">psychology</span>
                          Nemotron Architectural Critique &amp; Feedback
                        </span>
                        <div className="text-xs sm:text-sm text-on-surface leading-relaxed font-body-md bg-tertiary-container/10 p-3.5 rounded-lg border border-tertiary/20 whitespace-pre-line">
                          {q.feedback}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
