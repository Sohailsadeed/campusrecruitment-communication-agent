import { useEffect, useState, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { getGuesstimateReport, GuesstimateSessionResponse } from "../../api/guesstimate";

export default function GuesstimateReport() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<GuesstimateSessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPlayingTTS, setIsPlayingTTS] = useState(false);
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    getGuesstimateReport(Number(sessionId))
      .then((res) => {
        setData(res);
      })
      .catch((err: any) => {
        setError(err?.response?.data?.detail || "Failed to load guesstimate report.");
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
        <div className="w-12 h-12 rounded-full border-2 border-tertiary border-t-transparent animate-spin" />
        <span className="font-headline-sm text-sm text-on-surface-variant font-medium">
          Compiling Guesstimate Assessment Dossier...
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
        <p className="text-sm text-on-surface-variant max-w-md">{error || "Could not retrieve session dossier."}</p>
        <Link
          to="/guesstimate"
          className="px-5 py-2.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-headline-sm text-xs font-semibold transition-colors flex items-center gap-2 mt-2"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          <span>Return to Studio</span>
        </Link>
      </div>
    );
  }

  const evaluation = data.evaluation;
  const score = data.overall_score || evaluation?.overall_score || 0;

  // Verdict calculation
  let verdict = { text: "Needs Structuring Rigor", color: "text-rose-400 bg-rose-500/10 border-rose-500/20" };
  if (score >= 85) {
    verdict = { text: "MBB / Tier-1 Ready", color: "text-tertiary bg-tertiary/10 border-tertiary/30" };
  } else if (score >= 70) {
    verdict = { text: "Competitive Consultant", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" };
  } else if (score >= 55) {
    verdict = { text: "Promising Structure", color: "text-amber-400 bg-amber-500/10 border-amber-500/20" };
  }

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
      <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-tertiary/10 rounded-full blur-[140px] print:hidden" />
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-primary/10 rounded-full blur-[120px] print:hidden" />

      {/* Top Header & Breadcrumbs */}
      <div className="relative z-10 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-outline-variant/30 print:border-b-2 print:border-black/20">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 text-xs text-outline font-label-caps print:hidden">
            <Link to="/" className="hover:text-on-surface transition-colors">Practice Arena</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <Link to="/guesstimate" className="hover:text-on-surface transition-colors">Guesstimate Studio</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-tertiary font-semibold">Assessment Dossier</span>
          </div>

          <h1 className="font-display-hero text-2xl sm:text-4xl font-extrabold text-on-surface tracking-tight print:text-black">
            Guesstimate Evaluation Dossier
          </h1>

          <p className="text-sm text-on-surface-variant flex flex-wrap items-center gap-2 print:text-gray-700">
            <span>Category: <strong className="text-on-surface font-semibold print:text-black">{data.category}</strong></span>
            <span className="text-outline print:text-gray-400">•</span>
            <span>Difficulty: <strong className="text-tertiary font-semibold print:text-black">{data.difficulty}</strong></span>
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
            onClick={() => navigate("/guesstimate")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-tertiary hover:opacity-90 text-on-tertiary font-headline-sm text-xs font-bold transition-all shadow-md shadow-tertiary/20"
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            <span>New Drill</span>
          </button>
        </div>
      </div>

      {/* Case Problem Banner */}
      <div className="p-5 sm:p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-2 shadow-sm print:border-black/20 print:bg-gray-50">
        <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider">
          Problem Under Evaluation
        </span>
        <p className="font-headline-sm text-base sm:text-lg font-bold text-on-surface print:text-black leading-relaxed">
          "{data.question}"
        </p>
      </div>

      {/* Overall Score & 4 Telemetry Pillars */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-stretch">
        {/* Overall Score Card (4 Cols) */}
        <div className="md:col-span-4 p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-lg flex flex-col justify-between gap-4 print:border-black/20 print:bg-white">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-xs uppercase text-outline font-semibold">
              Consulting Evaluation Bar
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${verdict.color}`}>
              {verdict.text}
            </span>
          </div>

          <div className="flex items-baseline gap-2 my-2">
            <span className="font-display-hero text-6xl font-black text-on-surface print:text-black">
              {score}
            </span>
            <span className="text-xl text-outline font-label-numeric font-medium">/ 100</span>
          </div>

          <p className="text-xs text-on-surface-variant leading-relaxed">
            {evaluation?.executive_summary || "Guesstimate breakdown evaluated across MECE segmentation, proxy sanity, mental math flow, and reality checks."}
          </p>
        </div>

        {/* 4 Dimension Gauges (8 Cols) */}
        <div className="md:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* 1. MECE Structuring */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-tertiary text-[17px]">account_tree</span>
                MECE Structuring
              </span>
              <span className="font-label-numeric font-bold text-sm text-tertiary">
                {evaluation?.mece_score ?? 75}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.mece_feedback || "Good formula equation."}
            </p>
          </div>

          {/* 2. Proxy & Assumption Sanity */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-tertiary text-[17px]">verified</span>
                Assumption Sanity
              </span>
              <span className="font-label-numeric font-bold text-sm text-tertiary">
                {evaluation?.assumption_score ?? 75}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.assumption_feedback || "Realistic demographic proxies."}
            </p>
          </div>

          {/* 3. Mental Math Articulation */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-tertiary text-[17px]">calculate</span>
                Mental Math Flow
              </span>
              <span className="font-label-numeric font-bold text-sm text-tertiary">
                {evaluation?.mental_math_score ?? 75}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.math_feedback || "Calculations stated clearly out loud."}
            </p>
          </div>

          {/* 4. Sanity Check & Sensitivity */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-tertiary text-[17px]">balance</span>
                Sensitivity Analysis
              </span>
              <span className="font-label-numeric font-bold text-sm text-tertiary">
                {evaluation?.sanity_check_score ?? 70}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.sanity_check_feedback || "Tested against macro benchmark."}
            </p>
          </div>
        </div>
      </div>

      {/* Audio Playback & Submitted Transcript */}
      <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-sm print:break-inside-avoid print:border-black/20">
        <div className="flex items-center justify-between">
          <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[18px]">record_voice_over</span>
            Candidate Spoken Articulation &amp; Scratchpad
          </span>
          {data.audio_url && (
            <span className="text-xs text-outline font-label-numeric-sm flex items-center gap-1">
              <span className="material-symbols-outlined text-tertiary text-[15px]">mic</span>
              Recorded Spoken Voice
            </span>
          )}
        </div>

        {/* Audio Player */}
        {data.audio_url && (
          <div className="p-3.5 rounded-xl bg-surface-container border border-outline-variant/30 flex items-center gap-4 print:hidden">
            <audio controls src={data.audio_url} className="w-full h-9 rounded-lg" />
          </div>
        )}

        {/* Transcript Box */}
        <div className="p-4 rounded-xl bg-surface-container/60 border border-outline-variant/20 font-mono text-xs text-on-surface-variant leading-relaxed whitespace-pre-wrap max-h-60 overflow-y-auto">
          {data.candidate_answer || "No written transcript recorded."}
        </div>
      </div>

      {/* Model Consulting Breakdown Tree */}
      <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-5 shadow-lg print:break-inside-avoid print:border-black/20">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-tertiary/10 text-tertiary flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">account_tree</span>
            </div>
            <div>
              <span className="font-headline-sm text-sm font-bold text-on-surface block">
                Model Consulting Decomposition Tree
              </span>
              <span className="text-[11px] text-outline font-label-caps uppercase">
                {evaluation?.model_approach_name || "Optimal Framework"}
              </span>
            </div>
          </div>

          {evaluation?.plausible_industry_range && (
            <div className="px-3 py-1 rounded-lg bg-tertiary-container/20 border border-tertiary/30 text-tertiary text-xs font-semibold">
              Industry Range: {evaluation.plausible_industry_range}
            </div>
          )}
        </div>

        {/* Tree Step Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {evaluation?.model_breakdown_steps?.map((step, idx) => (
            <div
              key={idx}
              className="p-4 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col justify-between gap-3 relative"
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-label-numeric-sm px-2 py-0.5 rounded bg-surface-container-high text-outline">
                  Branch {idx + 1}
                </span>
                <span className="material-symbols-outlined text-outline text-[16px]">chevron_right</span>
              </div>

              <div>
                <span className="font-headline-sm text-xs font-bold text-on-surface block mb-1">
                  {step.step_name}
                </span>
                <span className="text-[11px] text-outline font-mono block leading-snug">
                  {step.formula_or_proxy}
                </span>
              </div>

              <div className="pt-2 border-t border-outline-variant/20">
                <span className="font-label-numeric text-xs font-bold text-tertiary">
                  {step.estimated_value}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Ideal 60-Second Verbal Script */}
      {evaluation?.ideal_verbal_script && (
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-3 shadow-sm print:break-inside-avoid print:border-black/20">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[18px]">model_training</span>
              Exemplary 60-Second Verbal Delivery Script
            </span>
            <button
              type="button"
              onClick={() => toggleTTS(evaluation.ideal_verbal_script)}
              className="flex items-center gap-1 text-xs text-tertiary font-semibold hover:underline print:hidden cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">
                {isPlayingTTS ? "volume_off" : "volume_up"}
              </span>
              <span>{isPlayingTTS ? "Stop TTS" : "Listen Verbal Delivery"}</span>
            </button>
          </div>

          <p className="text-xs sm:text-sm text-on-surface leading-relaxed italic bg-surface-container/60 p-4 rounded-xl border border-outline-variant/20">
            "{evaluation.ideal_verbal_script}"
          </p>
        </div>
      )}

      {/* Strengths & Actionable Areas for Improvement */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 print:break-inside-avoid">
        {/* Strengths */}
        <div className="p-5 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-3 print:border-black/20">
          <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[18px]">thumb_up</span>
            Demonstrated Strengths
          </span>
          <ul className="flex flex-col gap-2">
            {evaluation?.strengths?.map((s, idx) => (
              <li key={idx} className="text-xs text-on-surface-variant flex items-start gap-2">
                <span className="material-symbols-outlined text-tertiary text-[16px] mt-0.5">check_circle</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Weaknesses */}
        <div className="p-5 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-3 print:border-black/20">
          <span className="font-label-caps text-xs uppercase text-amber-400 font-bold tracking-wider flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[18px]">lightbulb</span>
            High-Impact Coaching Areas
          </span>
          <ul className="flex flex-col gap-2">
            {evaluation?.weaknesses?.map((w, idx) => (
              <li key={idx} className="text-xs text-on-surface-variant flex items-start gap-2">
                <span className="material-symbols-outlined text-amber-400 text-[16px] mt-0.5">arrow_forward</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
