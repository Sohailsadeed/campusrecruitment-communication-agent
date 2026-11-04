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
      {/* Print Stylesheet for Placement Cells */}
      <style>{`
        @media print {
          @page {
            size: A4;
            margin: 12mm 15mm;
          }
          * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          body {
            background: white !important;
            color: #111 !important;
          }
          nav, aside, header, .no-print, audio, button, .print\\:hidden {
            display: none !important;
          }
          .print\\:break-inside-avoid {
            break-inside: avoid !important;
            page-break-inside: avoid !important;
          }
        }
      `}</style>

      {/* Formal Recruiter / Placement Cell Dossier Header (Print-Only) */}
      <div className="hidden print:block mb-4 p-4 border-b-2 border-black/40">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-bold tracking-widest text-gray-500">
              SpeakFlow Campus Placement Analytics
            </span>
            <h1 className="text-xl font-bold text-black tracking-tight mt-0.5">Management Consulting Sizing Dossier</h1>
            <p className="text-xs text-gray-600">Round 3: Guesstimate &amp; Market Sizing — Multi-Rubric Candidate Evaluation</p>
          </div>
          <div className="text-right text-xs text-gray-700 font-mono">
            <div>Session Ref: #{sessionId}</div>
            <div>Evaluation Date: {data.created_at ? new Date(data.created_at).toLocaleDateString() : new Date().toLocaleDateString()}</div>
            <div className="font-bold text-black mt-1">Placement Tier: {verdict.text}</div>
          </div>
        </div>
      </div>

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

      {/* Overall Score & 4 Telemetry Pillars with Authoritative Weighting */}
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

          <div>
            <div className="flex items-baseline gap-2 my-2">
              <span className="font-display-hero text-6xl font-black text-on-surface print:text-black">
                {score}
              </span>
              <span className="text-xl text-outline font-label-numeric font-medium">/ 100</span>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-tertiary font-semibold mt-1">
              <span className="material-symbols-outlined text-[15px]">scale</span>
              <span>Deterministic Consulting Formula</span>
            </div>
            <p className="text-[10px] text-outline mt-0.5">
              35% MECE + 25% Assumptions + 20% Math + 20% Sanity Check
            </p>
          </div>

          <p className="text-xs text-on-surface-variant leading-relaxed">
            {evaluation?.executive_summary || "Guesstimate breakdown evaluated across MECE segmentation, proxy sanity, mental math flow, and reality checks."}
          </p>
        </div>

        {/* 4 Dimension Gauges (8 Cols) */}
        <div className="md:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* 1. MECE Structuring (35%) */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sky-400 text-[17px]">account_tree</span>
                MECE Structuring (35%)
              </span>
              <span className="font-label-numeric font-bold text-sm text-sky-400">
                {evaluation?.mece_score ?? 75}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.mece_feedback || "Good formula equation."}
            </p>
          </div>

          {/* 2. Proxy & Assumption Sanity (25%) */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-emerald-400 text-[17px]">verified</span>
                Assumption Sanity (25%)
              </span>
              <span className="font-label-numeric font-bold text-sm text-emerald-400">
                {evaluation?.assumption_score ?? 75}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.assumption_feedback || "Realistic demographic proxies."}
            </p>
          </div>

          {/* 3. Mental Math Flow (20%) */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-orange-400 text-[17px]">calculate</span>
                Mental Math Flow (20%)
              </span>
              <span className="font-label-numeric font-bold text-sm text-orange-400">
                {evaluation?.mental_math_score ?? 75}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.math_feedback || "Calculations stated clearly out loud."}
            </p>
          </div>

          {/* 4. Sanity Check & Sensitivity (20%) */}
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col justify-between gap-2 print:border-black/20">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-xs uppercase text-outline font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-amber-400 text-[17px]">balance</span>
                Sanity Check &amp; Reality (20%)
              </span>
              <span className="font-label-numeric font-bold text-sm text-amber-400">
                {evaluation?.sanity_check_score ?? 70}/100
              </span>
            </div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              {evaluation?.sanity_check_feedback || "Tested against macro benchmark."}
            </p>
          </div>
        </div>
      </div>

      {/* Priority 3: Candidate Estimate vs. Plausible Industry Range Reality Diagnostic */}
      {(() => {
        const candEst = evaluation?.candidate_estimate_structured;
        const plausRng = evaluation?.plausible_range_structured;
        const rangeDiag = evaluation?.range_diagnostic;

        const candFormatted = candEst?.formatted_display || evaluation?.candidate_final_estimate || "Estimated Value";
        const plausFormatted = plausRng?.formatted_display || evaluation?.plausible_industry_range || "Plausible Consulting Band";

        return (
          <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-5 shadow-md print:break-inside-avoid print:border-black/20">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-tertiary/10 text-tertiary flex items-center justify-center">
                  <span className="material-symbols-outlined text-[20px]">straighten</span>
                </div>
                <div>
                  <h3 className="font-headline-sm text-base font-bold text-on-surface">
                    Reality Check: Candidate Estimate vs. Plausible Industry Range
                  </h3>
                  <span className="text-xs text-outline">
                    Normalized comparison across matched units, timeframes, and market geographies.
                  </span>
                </div>
              </div>

              <span
                className={`self-start sm:self-center px-3 py-1 rounded-full text-xs font-bold border ${
                  rangeDiag?.status === "within_range"
                    ? "text-tertiary bg-tertiary/15 border-tertiary/30"
                    : rangeDiag?.status === "below_range"
                    ? "text-amber-400 bg-amber-400/15 border-amber-400/30"
                    : rangeDiag?.status === "above_range"
                    ? "text-rose-400 bg-rose-400/15 border-rose-400/30"
                    : "text-outline bg-surface-container border-outline-variant/30"
                }`}
              >
                {rangeDiag?.summary_label || "Range Audit"}
              </span>
            </div>

            {/* Normalized Horizontal Gauge */}
            <div className="p-5 rounded-xl bg-surface-container border border-outline-variant/20 flex flex-col gap-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-3.5 rounded-lg bg-surface-container-high/60 border border-outline-variant/20 flex flex-col">
                  <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">
                    Candidate Stated Estimate
                  </span>
                  <span className="font-mono text-lg font-bold text-on-surface mt-0.5">
                    {candFormatted}
                  </span>
                  {candEst?.unit && (
                    <span className="text-[10px] text-outline font-mono mt-0.5">
                      Normalized: {candEst.unit} • {candEst.period} • {candEst.geography}
                    </span>
                  )}
                </div>

                <div className="p-3.5 rounded-lg bg-surface-container-high/60 border border-outline-variant/20 flex flex-col">
                  <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">
                    Plausible Consulting Benchmark
                  </span>
                  <span className="font-mono text-lg font-bold text-tertiary mt-0.5">
                    {plausFormatted}
                  </span>
                  <span className="text-[10px] text-outline font-mono mt-0.5">
                    Source: {plausRng?.benchmark_source || "Industry Census & Public Market Sizing"}
                  </span>
                </div>
              </div>

              {/* Range Visual Strip */}
              {plausRng?.min != null && plausRng?.max != null && candEst?.value != null && rangeDiag?.unit_match && (
                <div className="pt-2">
                  <div className="flex items-center justify-between text-[11px] font-mono text-outline mb-1.5">
                    <span>Min: {plausRng.min.toLocaleString()}</span>
                    <span className="text-tertiary font-semibold">Mid: {(((plausRng.min + plausRng.max) / 2)).toLocaleString()}</span>
                    <span>Max: {plausRng.max.toLocaleString()}</span>
                  </div>
                  <div className="relative w-full h-4 rounded-full bg-surface-container-highest overflow-hidden border border-outline-variant/30">
                    <div className="absolute inset-y-0 left-1/4 right-1/4 bg-tertiary/25 border-x border-tertiary/60" />
                  </div>
                </div>
              )}

              {/* Reality Diagnostic Caveat */}
              <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/20 text-xs text-on-surface-variant flex items-start gap-2">
                <span className="material-symbols-outlined text-tertiary text-[18px] shrink-0 mt-0.5">verified</span>
                <p className="leading-relaxed">
                  {rangeDiag?.diagnostic_note ||
                    "Being inside the plausible range demonstrates numerical sanity, but must be accompanied by MECE structure to verify sound methodology."}
                </p>
              </div>
            </div>
          </div>
        );
      })()}

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

      {/* Priority 2: MECE Decomposition Trees (Candidate Audit + Reference Benchmark) */}
      <div className="space-y-6">
        {/* Candidate Branch Evidence Audit */}
        {evaluation?.candidate_branch_diagnostics && evaluation.candidate_branch_diagnostics.length > 0 && (
          <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg print:break-inside-avoid print:border-black/20">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-sky-400/10 text-sky-400 flex items-center justify-center">
                  <span className="material-symbols-outlined text-[20px]">fact_check</span>
                </div>
                <div>
                  <h3 className="font-headline-sm text-sm font-bold text-on-surface">
                    Candidate Segment Evidence Audit
                  </h3>
                  <span className="text-[11px] text-outline">
                    Evidence-backed classification reconstructed from candidate's spoken transcript.
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap text-[10px]">
                <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-medium">
                  🟢 Supported MECE
                </span>
                <span className="px-2 py-0.5 rounded bg-rose-500/15 text-rose-400 border border-rose-500/30 font-medium">
                  🔴 Overlap
                </span>
                <span className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 font-medium">
                  🟠 Omission
                </span>
                <span className="px-2 py-0.5 rounded bg-yellow-500/15 text-yellow-300 border border-yellow-500/30 font-medium">
                  🟡 Unsupported Proxy
                </span>
                <span className="px-2 py-0.5 rounded bg-surface-container-high text-outline border border-outline-variant/30 font-medium">
                  ⚪ Unclear Evidence
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {evaluation.candidate_branch_diagnostics.map((branch, idx) => {
                const getStatusMeta = (st: string) => {
                  switch (st) {
                    case "supported_mece":
                      return { label: "Supported MECE Segment", color: "text-emerald-400 bg-emerald-500/15 border-emerald-500/30", icon: "check_circle" };
                    case "confirmed_overlap":
                      return { label: "Confirmed Double Count / Overlap", color: "text-rose-400 bg-rose-500/15 border-rose-500/30", icon: "warning" };
                    case "omitted_segment":
                      return { label: "Material Omission", color: "text-amber-400 bg-amber-500/15 border-amber-500/30", icon: "error" };
                    case "unsupported_proxy":
                      return { label: "Unsupported Assumption", color: "text-yellow-300 bg-yellow-500/15 border-yellow-500/30", icon: "help" };
                    default:
                      return { label: "Unclear / Insufficient Evidence", color: "text-outline bg-surface-container-high border-outline-variant/30", icon: "info" };
                  }
                };
                const meta = getStatusMeta(branch.status);

                return (
                  <div
                    key={idx}
                    className="p-4 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col justify-between gap-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-headline-sm text-xs font-bold text-on-surface">
                        {branch.branch_name}
                      </span>
                      <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-bold border ${meta.color}`}>
                        <span className="material-symbols-outlined text-[12px]">{meta.icon}</span>
                        <span>{meta.label}</span>
                      </span>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div className="flex items-baseline justify-between text-[11px]">
                        <span className="text-outline">Formula / Proxy:</span>
                        <span className="font-mono text-on-surface-variant">{branch.formula_or_proxy || "Unspecified"}</span>
                      </div>
                      <div className="flex items-baseline justify-between text-[11px]">
                        <span className="text-outline">Branch Value:</span>
                        <span className="font-mono font-semibold text-tertiary">{branch.estimated_value || "—"}</span>
                      </div>
                    </div>

                    <p className="text-[11px] text-outline leading-snug pt-2 border-t border-outline-variant/20 italic">
                      "{branch.evidence_rationale}"
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Consulting Reference Benchmark Tree (Proposal) */}
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-5 shadow-lg print:break-inside-avoid print:border-black/20">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-tertiary/10 text-tertiary flex items-center justify-center">
                <span className="material-symbols-outlined text-[20px]">account_tree</span>
              </div>
              <div>
                <span className="font-headline-sm text-sm font-bold text-on-surface block">
                  Consulting Reference Benchmark Tree (Reference Proposal)
                </span>
                <span className="text-[11px] text-outline font-label-caps uppercase">
                  {evaluation?.model_approach_name || "Optimal Framework"} • One valid gold-standard consulting decomposition
                </span>
              </div>
            </div>
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
                    Step {idx + 1}
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
      </div>

      {/* Priority 4: Deterministic Sensitivity Simulation & Tornado Ranking Panel */}
      {(() => {
        const sensitivity = evaluation?.sensitivity_analysis;
        const ranking = sensitivity?.tornado_ranking || [];
        const hasTornado = ranking.length > 1;

        return (
          <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-5 shadow-md print:break-inside-avoid print:border-black/20">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-amber-400/10 text-amber-400 flex items-center justify-center">
                  <span className="material-symbols-outlined text-[20px]">tune</span>
                </div>
                <div>
                  <h3 className="font-headline-sm text-base font-bold text-on-surface">
                    {hasTornado ? "Deterministic Sensitivity Analysis & Tornado Ranking" : "Deterministic Sensitivity Analysis & Leverage Drivers"}
                  </h3>
                  <span className="text-xs text-outline">
                    {hasTornado
                      ? "Ranks candidate assumptions by estimation volatility to prioritize interview defense."
                      : "Measures which equation variable most impacts the final sizing estimation."}
                  </span>
                </div>
              </div>

              {sensitivity?.impact_percent != null && (
                <span className="self-start sm:self-center px-3 py-1 rounded-full text-xs font-bold border border-amber-400/30 bg-amber-400/15 text-amber-400">
                  ±{sensitivity.impact_percent}% Peak Estimation Volatility
                </span>
              )}
            </div>

            {sensitivity?.status === "computed" ? (
              <div className="space-y-4">
                {/* Tornado Comparison Bar Chart (when 2+ drivers available) */}
                {hasTornado && (
                  <div className="p-4 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col gap-3">
                    <span className="font-label-caps text-[10px] uppercase text-outline font-bold tracking-wider">
                      Assumption Volatility Ranking (Mini Tornado Comparison)
                    </span>

                    <div className="space-y-3">
                      {ranking.map((item, idx) => (
                        <div key={idx} className="space-y-1.5">
                          <div className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-2">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${idx === 0 ? "bg-amber-400/20 text-amber-400 border border-amber-400/30" : "bg-surface-container-high text-outline border border-outline-variant/30"}`}>
                                #{item.rank} {item.role_label}
                              </span>
                              <strong className="text-on-surface">{item.driver_name}</strong>
                              <span className="text-[11px] text-outline font-mono">
                                ({item.baseline_driver_value} {item.driver_unit} baseline)
                              </span>
                            </div>
                            <span className="font-mono font-bold text-amber-400">
                              ±{item.impact_percent}% swing
                            </span>
                          </div>

                          {/* Relative Volatility Bar */}
                          <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${idx === 0 ? "bg-gradient-to-r from-amber-500 to-amber-300" : "bg-gradient-to-r from-sky-500/70 to-sky-300/70"}`}
                              style={{ width: `${Math.max(15, item.relative_bar_percent)}%` }}
                            />
                          </div>

                          {/* Scenario Mini Summary */}
                          <div className="flex items-center justify-between text-[11px] text-outline font-mono pt-0.5">
                            <span>Floor: {item.conservative_scenario?.label} ({item.conservative_scenario?.resulting_estimate?.toLocaleString()})</span>
                            <span>Ceiling: {item.aggressive_scenario?.label} ({item.aggressive_scenario?.resulting_estimate?.toLocaleString()})</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Scenario Cards (Conservative Floor, Candidate Baseline, Aggressive Ceiling) */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
                  {/* Conservative Scenario */}
                  <div className="p-4 rounded-xl bg-surface-container border border-outline-variant/20 flex flex-col justify-between">
                    <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">
                      Low Scenario ({sensitivity.low_driver_value} {sensitivity.driver_unit})
                    </span>
                    <span className="font-mono text-lg font-bold text-amber-400 my-1">
                      {sensitivity.low_estimate?.toLocaleString()}
                    </span>
                    <span className="text-[10px] text-outline">Conservative floor</span>
                  </div>

                  {/* Baseline Candidate Scenario */}
                  <div className="p-4 rounded-xl bg-surface-container-high border border-tertiary/30 flex flex-col justify-between">
                    <span className="font-label-caps text-[10px] uppercase text-tertiary font-bold">
                      Baseline Driver: {sensitivity.driver_name} ({sensitivity.baseline_driver_value} {sensitivity.driver_unit})
                    </span>
                    <span className="font-mono text-xl font-bold text-on-surface my-1">
                      {sensitivity.baseline_estimate?.toLocaleString()}
                    </span>
                    <span className="text-[10px] text-tertiary font-medium">Candidate baseline estimate</span>
                  </div>

                  {/* Aggressive Scenario */}
                  <div className="p-4 rounded-xl bg-surface-container border border-outline-variant/20 flex flex-col justify-between">
                    <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">
                      High Scenario ({sensitivity.high_driver_value} {sensitivity.driver_unit})
                    </span>
                    <span className="font-mono text-lg font-bold text-emerald-400 my-1">
                      {sensitivity.high_estimate?.toLocaleString()}
                    </span>
                    <span className="text-[10px] text-outline">Aggressive ceiling</span>
                  </div>
                </div>

                {/* Consulting Defense Guidance Advice */}
                <div className="p-3.5 rounded-xl bg-surface-container/60 border border-outline-variant/20 text-xs text-on-surface-variant flex items-start gap-2">
                  <span className="material-symbols-outlined text-amber-400 text-[18px] shrink-0 mt-0.5">lightbulb</span>
                  <div>
                    <strong className="text-on-surface block mb-0.5 font-semibold">Consulting Interview Defense Advice:</strong>
                    <p className="leading-relaxed">
                      {sensitivity.multi_driver_guidance || sensitivity.explanation}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-surface-container/60 border border-outline-variant/20 text-xs text-outline flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">info</span>
                <span>
                  {sensitivity?.explanation || "Candidate formula was not sufficiently articulated with numeric proxies to perform deterministic sensitivity modeling."}
                </span>
              </div>
            )}
          </div>
        );
      })()}

      {/* Ideal 60-Second Verbal Script */}
      {evaluation?.ideal_verbal_script && (
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-3 shadow-sm print:break-inside-avoid print:border-black/20">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[18px]">model_training</span>
              Illustrative 60-Second Verbal Delivery Model (Benchmark Example)
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
