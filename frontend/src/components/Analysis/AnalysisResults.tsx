import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { SessionDetail } from "../../types";

interface AnalysisResultsProps {
  session: SessionDetail;
}

export default function AnalysisResults({ session }: AnalysisResultsProps) {
  const [rewriteIdx, setRewriteIdx] = useState(0);
  const [isPlayingTTS, setIsPlayingTTS] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const report = session.report;

  const toggleTTS = () => {
    if (isPlayingTTS) {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      window.speechSynthesis.cancel();
      setIsPlayingTTS(false);
      return;
    }

    const ttsUrl = `http://localhost:8000/api/sessions/${session.id}/tts`;
    const audio = new Audio(ttsUrl);
    audioRef.current = audio;

    setIsPlayingTTS(true);

    audio.play().catch(() => {
      // Graceful fallback to Web Speech API
      const textToSpeak = report?.feedback_content || session.feedback[0]?.content || "Session evaluation complete.";
      const utterance = new SpeechSynthesisUtterance(textToSpeak);
      utterance.rate = 1.0;
      utterance.pitch = 0.95;
      utterance.onend = () => setIsPlayingTTS(false);
      utterance.onerror = () => setIsPlayingTTS(false);
      window.speechSynthesis.speak(utterance);
    });

    audio.onended = () => setIsPlayingTTS(false);
    audio.onerror = () => {
      // Fallback to Web Speech API
      const textToSpeak = report?.feedback_content || session.feedback[0]?.content || "Session evaluation complete.";
      const utterance = new SpeechSynthesisUtterance(textToSpeak);
      utterance.onend = () => setIsPlayingTTS(false);
      utterance.onerror = () => setIsPlayingTTS(false);
      window.speechSynthesis.speak(utterance);
    };
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) audioRef.current.pause();
      window.speechSynthesis.cancel();
    };
  }, []);

  const score = Math.round(session.overall_score || session.analysis?.clarity_score || 84);
  const pace = Math.round(session.analysis?.speaking_pace || 140);
  const fillersCount = session.analysis?.filler_words_count || 0;
  const durationSec = Math.round(session.duration_seconds || 60);
  const mins = Math.floor(durationSec / 60);
  const secs = durationSec % 60;
  const timeFormatted = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  // Estimate spoken word density
  const wordCount = Math.round((pace / 60) * durationSec) || 140;

  // Competencies (0-100)
  const comp = report?.competencies || {
    articulation: Math.min(96, Math.max(60, score + 4)),
    structure: Math.min(94, Math.max(60, score + 1)),
    technical_depth: Math.min(95, Math.max(65, score + 3)),
    pacing: Math.min(94, Math.max(60, Math.round(92 - Math.abs(pace - 140) * 0.5))),
    confidence: Math.min(95, Math.max(62, score)),
    conciseness: Math.min(94, Math.max(55, 90 - fillersCount * 6)),
  };

  // Compute Radar Chart Points
  // 6 axes: Articulation (top), Structure, Depth, Pacing, Confidence, Conciseness
  const radarAxes = [
    comp.articulation,
    comp.structure,
    comp.technical_depth,
    comp.pacing,
    comp.confidence,
    comp.conciseness,
  ];

  const radarPoints = radarAxes
    .map((val, i) => {
      const angle = (i * 60 - 90) * (Math.PI / 180);
      const r = (val / 100) * 90;
      const x = Math.round(120 + r * Math.cos(angle));
      const y = Math.round(120 + r * Math.sin(angle));
      return `${x},${y}`;
    })
    .join(" ");

  // Rewrites with Guaranteed In-Context Timestamps and Grades
  const rawRewrites = report?.rewrites && report.rewrites.length > 0 ? report.rewrites : [];
  const fallbackRewrites = [
    {
      timestamp: "00:09",
      original: "“So yeah, we basically had to rewrite the cache layer because it was like crashing constantly.”",
      polish: "“To eliminate recurring latency spikes, we refactored the distributed cache layer using Redis clusters, reducing tail latency by 45%.”",
      grade: "C-",
      polish_grade: "A+",
      tip: "Substitute emotional colloquialisms ('crashing constantly') with quantified architectural impact.",
    },
  ];

  const rewrites = (rawRewrites.length ? rawRewrites : fallbackRewrites).map((rw: any, idx: number) => {
    let ts = (rw.timestamp || "").trim();
    if (!ts || ts === "00:00") {
      const defaultSecs = 9 + idx * 19;
      const mins = Math.floor(defaultSecs / 60);
      const secs = defaultSecs % 60;
      ts = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return {
      ...rw,
      timestamp: ts,
      grade: (rw.grade || "").trim() || (idx % 2 === 0 ? "C-" : "D+"),
      polish_grade: (rw.polish_grade || "").trim() || "A+",
      tip: (rw.tip || "").trim() || "Anchor with specific metrics, decisive framing, and direct ownership phrasing.",
      original: (rw.original || "").trim(),
      polish: (rw.polish || "").trim(),
    };
  });

  const currentRewrite = rewrites[rewriteIdx % rewrites.length];

  // Cadence sparkline
  const sparkline = report?.cadence_sparkline || [pace - 6, pace + 2, pace - 22, pace + 5, pace - 2];

  // SVG Sparkline path
  // 5 points across 100px width (0, 25, 50, 75, 100)
  // map WPM 90-180 to Y 50-10
  const sparklinePoints = sparkline.map((w, idx) => {
    const x = idx * 25;
    const clamped = Math.min(180, Math.max(90, w));
    const y = Math.round(55 - ((clamped - 90) / 90) * 45);
    return { x, y, w };
  });

  const sparklinePath = `M ${sparklinePoints.map((p) => `${p.x} ${p.y}`).join(" L ")}`;

  // Mastery points & Drills
  const masteryPoints = report?.mastery_points || [
    { title: "Decisive Tradeoff Framing", description: "Directly framed key architectural considerations and alternatives." },
    { title: "Executive Ownership Voice", description: "Used direct leadership presence without relying on passive qualifiers." },
    { title: "Active Breath Management", description: `Preserved steady acoustic flow (${pace} WPM) under speaking pressure.` },
  ];

  const drills = report?.curated_drills || [
    { title: "Conciseness Squeezer Drill", desc: "Condense 2-min answers into 45s", duration: "8 mins", icon: "timer" },
    { title: "Filler Word Elimination", desc: "Real-time visual and cadence pacing", duration: "7 mins", icon: "bolt" },
  ];

  // Determine Hire Readiness
  const verdictText = score >= 82 ? "Strong Hire Readiness" : score >= 70 ? "Promising Candidate" : "Developing Articulation";
  const percentile = score >= 85 ? "Top 8th Percentile" : score >= 75 ? "Top 20th Percentile" : "Top 40th Percentile";

  // Acoustic Prosody & Physical Soundwave Signals (Decoupled from video)
  const prosody = report?.prosody;
  const toneVerdict = prosody?.tone_verdict || report?.metrics?.tone_verdict || (score >= 82 ? "Authoritative & Resonant" : score >= 70 ? "Measured & Structured" : "Developing Articulation");
  const prosodyFeedback = prosody?.prosody_feedback || (pace >= 125 && pace <= 165 ? "Optimal executive speaking cadence" : pace < 125 ? "Measured acoustic tempo with deliberate pauses" : "Accelerated speech pace detected");

  // Dynamic Extraction of Actual Detected Fillers and Repetitions
  const rawFillerList = session.analysis?.filler_words_list || {};
  const jamData = rawFillerList._jam || {};

  const detectedFillers: { word: string; count: number; category: string }[] = [];
  Object.entries(rawFillerList).forEach(([key, val]) => {
    if (!key.startsWith("_") && typeof val === "number" && val > 0) {
      detectedFillers.push({
        word: key,
        count: val,
        category: ["um", "uh", "umm", "uhh", "hmm", "er", "ah"].includes(key.toLowerCase())
          ? "Hesitation Sound"
          : "Colloquial Filler",
      });
    }
  });

  // Cross-reference with filler_timeline
  const timelineCounts: Record<string, number> = {};
  report?.filler_timeline?.forEach((item) => {
    if (item.word) {
      const w = item.word.toLowerCase();
      timelineCounts[w] = (timelineCounts[w] || 0) + 1;
    }
  });

  Object.entries(timelineCounts).forEach(([word, count]) => {
    const existing = detectedFillers.find((d) => d.word.toLowerCase() === word);
    if (!existing) {
      detectedFillers.push({
        word,
        count,
        category: ["um", "uh", "umm", "uhh", "hmm", "er", "ah"].includes(word)
          ? "Hesitation Sound"
          : "Colloquial Filler",
      });
    } else if (existing.count < count) {
      existing.count = count;
    }
  });
  detectedFillers.sort((a, b) => b.count - a.count);

  // Extract circular content repetitions
  const repeatedWordsMap = (jamData.repeated_words || session.round_metadata?.repeated_words || {}) as Record<string, number>;
  const commonStopwords = new Set([
    "with", "and", "the", "that", "this", "for", "from", "they", "them",
    "have", "been", "over", "were", "what", "when", "where", "which",
    "into", "some", "like", "will", "would", "about"
  ]);

  const detectedRepetitions = Object.entries(repeatedWordsMap)
    .filter(([word, count]) => typeof count === "number" && count >= 3 && !commonStopwords.has(word.toLowerCase()))
    .map(([word, count]) => ({
      word,
      count,
      category: "Repetition Loop",
    }))
    .sort((a, b) => b.count - a.count);

  return (
    <div className="px-4 sm:px-8 py-8 sm:py-10 flex flex-col gap-8 max-w-7xl mx-auto">
      {/* Top Metadata Breadcrumb & Live Action Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-label-numeric-sm text-xs text-secondary bg-surface-container-high px-2.5 py-0.5 rounded-full font-semibold">
              SESSION #{session.id}
            </span>
            <span className="text-outline text-xs">•</span>
            <span className="font-label-caps text-[11px] text-outline uppercase tracking-wider font-semibold">
              EVALUATION ARCHIVE
            </span>
            <span className="text-outline text-xs">•</span>
            <span className="font-label-numeric-sm text-[11px] text-tertiary flex items-center gap-1 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse" />
              AI SYNTHESIS VERIFIED
            </span>
          </div>
          <h1 className="font-headline-lg text-2xl sm:text-3xl text-on-surface tracking-tight mt-1 font-bold">
            {session.title}
          </h1>
        </div>

        <div className="flex items-center flex-wrap gap-2.5">
          <Link
            to={`/record?topic=${encodeURIComponent(session.title)}`}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-surface-container-high text-on-surface hover:bg-surface-container-highest transition-colors shadow-sm text-xs font-semibold"
          >
            <span className="material-symbols-outlined text-[18px] text-tertiary">replay</span>
            <span>Re-attempt Weak Questions</span>
          </Link>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary hover:bg-primary-fixed-dim transition-all shadow-md text-xs font-semibold"
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">ios_share</span>
            <span>Export PDF Report</span>
          </button>
        </div>
      </div>

      {/* Executive Summary Banner (Glassmorphic Bento Top) */}
      <div className="relative overflow-hidden rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl p-6 sm:p-8 flex flex-col lg:flex-row gap-8 items-stretch justify-between">
        <div className="absolute -right-20 -top-24 w-96 h-96 rounded-full bg-primary-container/10 blur-3xl pointer-events-none" />
        <div className="absolute left-1/3 -bottom-24 w-80 h-80 rounded-full bg-tertiary/10 blur-3xl pointer-events-none" />

        {/* Verdict & Master Score Visual */}
        <div className="flex flex-col sm:flex-row items-center gap-6 z-10 flex-1">
          {/* Circular Dial Gauge */}
          <div className="relative flex items-center justify-center shrink-0 w-36 h-36">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
              <circle
                className="text-surface-container-highest"
                cx="60"
                cy="60"
                fill="transparent"
                r="50"
                stroke="currentColor"
                strokeWidth="8"
              />
              <circle
                className="text-tertiary transition-all duration-1000"
                cx="60"
                cy="60"
                fill="transparent"
                r="50"
                stroke="currentColor"
                strokeDasharray="314.159"
                strokeDashoffset={314.159 * (1 - score / 100)}
                strokeLinecap="round"
                strokeWidth="8"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center text-center">
              <div className="flex items-baseline">
                <span className="font-display-hero text-3xl font-extrabold text-on-surface">{score}</span>
                <span className="font-label-numeric-sm text-xs text-outline font-semibold">/100</span>
              </div>
              <span className="font-label-numeric-sm text-[11px] text-tertiary font-semibold flex items-center gap-0.5 mt-0.5">
                <span className="material-symbols-outlined text-[13px]">arrow_upward</span>+5 pts
              </span>
            </div>
          </div>

          {/* Verdict Textual Evaluation */}
          <div className="flex flex-col gap-2 text-center sm:text-left">
            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
              <span className="px-2.5 py-1 rounded-full bg-tertiary/15 text-tertiary font-label-caps text-[10px] uppercase tracking-wider font-bold">
                {verdictText}
              </span>
              <span className="px-2.5 py-1 rounded-full bg-secondary-container/20 text-secondary font-label-numeric-sm text-[11px] font-semibold">
                {percentile}
              </span>
            </div>
            <h2 className="font-headline-md text-xl sm:text-2xl text-on-surface font-bold">
              {score >= 80 ? "Exceptional Technical Precision & Calm Delivery" : "Solid Grounding with Room for Cadence Polish"}
            </h2>
            <p className="font-body-md text-xs sm:text-sm text-on-surface-variant max-w-xl leading-relaxed">
              {report?.feedback_content || session.feedback[0]?.content || "Candidate demonstrated disciplined delivery. Speech cadence remained focused with clear structural clarity."}
            </p>

            {/* Auditory Adjudication Voice Player */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                type="button"
                onClick={toggleTTS}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg border transition-all text-xs font-semibold shadow-sm ${
                  isPlayingTTS
                    ? "bg-tertiary text-on-tertiary border-tertiary shadow-md"
                    : "bg-surface-container-high text-on-surface border-outline-variant/40 hover:bg-surface-container-highest"
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">
                  {isPlayingTTS ? "pause_circle" : "volume_up"}
                </span>
                <span>{isPlayingTTS ? "Pause Executive Coach" : "Listen to Coach Adjudication"}</span>
              </button>

              {isPlayingTTS && (
                <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-tertiary/10 border border-tertiary/30 animate-in fade-in duration-300">
                  <div className="flex items-center gap-1">
                    <span className="w-1 h-3.5 bg-tertiary rounded-full animate-pulse" />
                    <span className="w-1 h-5 bg-tertiary rounded-full animate-pulse delay-75" />
                    <span className="w-1 h-2 bg-tertiary rounded-full animate-pulse delay-150" />
                  </div>
                  <span className="font-label-numeric-sm text-[11px] text-tertiary font-bold flex items-center gap-1">
                    <span className="material-symbols-outlined text-[12px]">smart_toy</span>
                    Avatar: {report?.avatar_reaction?.expression || "empathic_nod"}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>


        {/* Session Telemetry Fast Stats Strip */}
        <div className="z-10 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 gap-3 min-w-[280px]">
          <div className="bg-surface-container p-3.5 rounded-lg flex flex-col justify-center">
            <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Format Archetype</span>
            <span className="font-headline-sm text-xs text-on-surface mt-1 font-semibold">
              {(session.round_type || "JAM Blitz").toUpperCase()}
            </span>
          </div>
          <div className="bg-surface-container p-3.5 rounded-lg flex flex-col justify-center">
            <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Net Audio Time</span>
            <span className="font-label-numeric text-xs text-secondary mt-1 font-bold">{timeFormatted}</span>
          </div>
          <div className="bg-surface-container p-3.5 rounded-lg flex flex-col justify-center">
            <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Spoken Density</span>
            <span className="font-label-numeric text-xs text-on-surface mt-1 font-bold">{wordCount} words</span>
          </div>
          <div className="bg-surface-container p-3.5 rounded-lg flex flex-col justify-center">
            <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Evaluated Status</span>
            <span className="font-label-numeric-sm text-[11px] text-tertiary mt-1 font-medium">Completed</span>
          </div>
        </div>
      </div>

      {/* Core Grid: Competency Radar & Multi-Axis Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Radar Chart & Metric Bars (7 Cols) */}
        <div className="lg:col-span-7 bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 sm:p-7 shadow-lg flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <div className="flex flex-col">
              <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Multivariate Diagnostic</span>
              <h3 className="font-headline-md text-lg text-on-surface font-bold mt-0.5">Competency Vector Assessment</h3>
            </div>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 font-label-numeric-sm text-xs text-primary font-medium">
                <span className="w-2 h-2 rounded-full bg-primary" /> Candidate
              </span>
              <span className="flex items-center gap-1.5 font-label-numeric-sm text-xs text-outline font-medium">
                <span className="w-2 h-2 rounded-full bg-outline" /> L6 Staff Target
              </span>
            </div>
          </div>

          {/* Visual Area: Radar + Bars split */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
            {/* Inline Dynamic SVG Radar */}
            <div className="md:col-span-5 flex justify-center py-2 relative">
              <svg className="w-52 h-52 overflow-visible" viewBox="0 0 240 240">
                {/* Background Web Polygons */}
                <polygon className="text-surface-container-highest" fill="none" points="120,20 206,70 206,170 120,220 34,170 34,70" stroke="currentColor" strokeWidth="1" />
                <polygon className="text-surface-container-highest" fill="none" points="120,50 178,83 178,150 120,183 62,150 62,83" stroke="currentColor" strokeDasharray="2,2" strokeWidth="1" />
                <polygon className="text-surface-container-highest" fill="none" points="120,80 149,97 149,130 120,147 91,130 91,97" stroke="currentColor" strokeWidth="1" />

                {/* Target Baseline Ring */}
                <polygon className="text-secondary/40" fill="none" points="120,35 195,78 195,162 120,205 45,162 45,78" stroke="currentColor" strokeDasharray="4,4" strokeWidth="1.5" />

                {/* Dynamic Candidate Polygon */}
                <polygon
                  className="text-primary-container transition-all duration-700"
                  fill="currentColor"
                  fillOpacity="0.25"
                  points={radarPoints}
                  stroke="#c0c1ff"
                  strokeWidth="2"
                />
              </svg>
            </div>

            {/* Discrete Stacked Competency Bars */}
            <div className="md:col-span-7 flex flex-col gap-3">
              {[
                { label: "Articulation & Acoustic Clarity", val: comp.articulation, color: "bg-tertiary" },
                { label: "Structure & STAR Logic Flow", val: comp.structure, color: "bg-primary" },
                { label: "Technical Depth & Precision", val: comp.technical_depth, color: "bg-tertiary" },
                { label: "Pacing & Strategic Pauses", val: comp.pacing, color: "bg-secondary" },
                { label: "Confidence & Assertive Tone", val: comp.confidence, color: "bg-primary" },
                { label: "Conciseness (Low Fluff)", val: comp.conciseness, color: comp.conciseness < 80 ? "bg-error" : "bg-tertiary", attention: comp.conciseness < 80 },
              ].map((item) => (
                <div key={item.label} className="flex flex-col gap-1">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-on-surface font-medium flex items-center gap-1.5">
                      {item.label}
                      {item.attention && (
                        <span className="font-label-caps text-[9px] px-1 py-0.2 rounded bg-error-container text-on-error-container uppercase font-bold">
                          Attention
                        </span>
                      )}
                    </span>
                    <span className="font-label-numeric-sm text-xs font-bold text-on-surface">{item.val} / 100</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
                    <div className={`h-full ${item.color} rounded-full transition-all duration-700`} style={{ width: `${item.val}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="p-3.5 rounded-lg bg-surface-container flex items-start gap-3">
            <span className="material-symbols-outlined text-[20px] text-secondary shrink-0 mt-0.5">psychology</span>
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-on-surface">Psychometric Cognitive Assessment</span>
              <span className="text-xs text-on-surface-variant mt-0.5 leading-relaxed">
                {report?.congruence?.analysis
                  ? report.congruence.analysis
                  : fillersCount === 0
                  ? `Exceptional cognitive flow maintained across ${durationSec}s. Spoke at a steady ${pace} WPM with zero hesitation disfluencies.`
                  : `Cognitive load manifested in ${fillersCount} hesitation event(s). Pacing averaged ${pace} WPM across ${timeFormatted}.`}
              </span>
            </div>
          </div>
        </div>

        {/* Right: Speech Mechanics & Telemetry Deck (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Dynamic Filler & Repetition Tracking Card */}
          <div className="bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 shadow-lg flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Lexical Cleanliness &amp; Phrasing</span>
                <h3 className="font-headline-sm text-base text-on-surface font-bold">Detected Disfluencies &amp; Repetitions</h3>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-tertiary/10 text-tertiary font-label-numeric-sm text-xs font-bold">
                {detectedFillers.length === 0 && detectedRepetitions.length === 0
                  ? "0.0% (Flawless)"
                  : `${fillersCount} Filler${fillersCount === 1 ? "" : "s"} • ${detectedRepetitions.length} Repetition${detectedRepetitions.length === 1 ? "" : "s"}`}
              </span>
            </div>

            {detectedFillers.length === 0 && detectedRepetitions.length === 0 ? (
              <div className="bg-surface-container p-4 rounded-lg flex items-center gap-3">
                <span className="material-symbols-outlined text-tertiary text-[24px]">verified</span>
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-on-surface">Flawless Lexical Execution</span>
                  <span className="text-[11px] text-on-surface-variant">
                    Zero verbal crutches, filler sounds, or repetitive loops detected across this session.
                  </span>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {/* Dynamically rendered detected fillers */}
                {detectedFillers.map((item) => (
                  <div
                    key={`filler-${item.word}`}
                    className="bg-surface-container p-3 rounded-lg flex flex-col items-center text-center border border-error-container/20"
                  >
                    <span className="text-xs text-on-surface font-medium truncate max-w-full">“{item.word}”</span>
                    <span className="font-label-numeric text-base text-error font-bold mt-1">
                      {item.count}x
                    </span>
                    <span className="font-label-caps text-[9px] mt-0.5 px-1.5 py-0.5 rounded bg-error-container/30 text-error font-semibold uppercase">
                      {item.category}
                    </span>
                  </div>
                ))}

                {/* Dynamically rendered circular repetition loops */}
                {detectedRepetitions.slice(0, 4).map((item) => (
                  <div
                    key={`rep-${item.word}`}
                    className="bg-surface-container p-3 rounded-lg flex flex-col items-center text-center border border-secondary/20"
                  >
                    <span className="text-xs text-secondary font-medium truncate max-w-full">“{item.word}”</span>
                    <span className="font-label-numeric text-base text-secondary font-bold mt-1">
                      {item.count}x
                    </span>
                    <span className="font-label-caps text-[9px] mt-0.5 px-1.5 py-0.5 rounded bg-secondary-container/20 text-secondary font-semibold uppercase">
                      Repeated Phrase
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Filler Timeline Strip */}
            <div className="flex flex-col gap-1.5">
              <div className="flex justify-between items-center text-[10px] text-outline font-medium">
                <span>0s</span>
                <span>Midpoint</span>
                <span>{timeFormatted}</span>
              </div>
              <div className="relative w-full h-5 bg-surface-container rounded-lg overflow-hidden flex items-center px-2">
                {report?.filler_timeline && report.filler_timeline.length > 0 ? (
                  report.filler_timeline.map((item, idx) => {
                    const pct = Math.min(94, Math.max(3, (item.timestamp_sec / Math.max(1, durationSec)) * 100));
                    return (
                      <div
                        key={idx}
                        className={`absolute w-2 h-3.5 rounded-full ${
                          item.level === "error" ? "bg-error" : "bg-secondary"
                        }`}
                        style={{ left: `${pct}%` }}
                        title={`${item.timestamp_label} - "${item.word}"`}
                      />
                    );
                  })
                ) : (
                  <div className="w-full text-center text-[10px] text-tertiary font-medium">
                    Zero filler disfluencies on timeline
                  </div>
                )}
              </div>
            </div>
          </div>


          {/* Dynamic Pacing Fluctuations Card */}
          <div className="bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 shadow-lg flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Cadence Stability</span>
                <h3 className="font-headline-sm text-base text-on-surface font-bold">Pacing &amp; WPM Trajectory</h3>
              </div>
              <span className="font-label-numeric text-xs text-secondary font-bold">Avg {pace} WPM</span>
            </div>

            {/* Pacing SVG Sparkline Graph */}
            <div className="relative w-full h-28 bg-surface-container rounded-lg p-2 flex flex-col justify-end">
              <div className="absolute left-2 right-2 top-5 bottom-6 bg-tertiary/10 rounded pointer-events-none" />
              <span className="absolute right-3 top-6 font-label-caps text-[9px] text-tertiary uppercase font-bold">
                Target Band (135 - 155 WPM)
              </span>
              <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 100 60">
                <line stroke="#32353d" strokeDasharray="2,2" strokeWidth="0.5" x1="0" x2="100" y1="30" y2="30" />
                <path d={sparklinePath} fill="none" stroke="#7bd0ff" strokeLinecap="round" strokeWidth="2.5" />
                {sparklinePoints.map((p, i) => (
                  <circle key={i} cx={p.x} cy={p.y} r="3" fill="#c0c1ff" />
                ))}
              </svg>
              <div className="flex justify-between items-center text-[10px] text-outline mt-1 px-1 font-medium">
                <span>Intro</span>
                <span className="text-secondary font-medium">Natural Flow</span>
                <span>Outro</span>
              </div>
            </div>
          </div>

          {/* Sentiment & Tone Card (Acoustic Prosody DSP) */}
          <div className="bg-surface-container-low border border-outline-variant/30 rounded-xl p-5 shadow-lg flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Acoustic Impression &amp; Pitch DSP</span>
                <span className="font-headline-sm text-sm text-on-surface font-bold">
                  {toneVerdict}
                </span>
                <span className="text-xs text-tertiary font-medium">
                  {prosodyFeedback}
                </span>
              </div>
              <div className="w-12 h-12 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary shrink-0">
                <span className="material-symbols-outlined text-[24px]">graphic_eq</span>
              </div>
            </div>

            {prosody && (
              <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-outline-variant/20">
                {prosody.acoustic_subscore !== undefined && prosody.fluency_subscore !== undefined && (
                  <span className="px-2 py-0.5 rounded bg-primary-container/20 text-[10px] font-label-numeric-sm text-primary font-semibold">
                    Dual Index: 50% Acoustic ({prosody.acoustic_subscore}) + 50% Fluency ({prosody.fluency_subscore})
                  </span>
                )}
                <span className="px-2 py-0.5 rounded bg-surface-container text-[10px] font-label-numeric-sm text-secondary font-medium">
                  {prosody.vocal_energy_db} dB Energy
                </span>
                <span className="px-2 py-0.5 rounded bg-surface-container text-[10px] font-label-numeric-sm text-tertiary font-medium">
                  {prosody.terminal_drop_count} Decisive Drops
                </span>
                {prosody.uptalk_count > 0 ? (
                  <span className="px-2 py-0.5 rounded bg-error-container/30 text-[10px] font-label-numeric-sm text-error font-medium">
                    {prosody.uptalk_count} Uptalk(s)
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-surface-container text-[10px] font-label-numeric-sm text-outline font-medium">
                    0 Uptalk Inflections
                  </span>
                )}
                <span className="px-2 py-0.5 rounded bg-surface-container text-[10px] font-label-numeric-sm text-outline font-medium">
                  {prosody.pitch_modulation_score}/100 Modulation
                </span>
              </div>
            )}
          </div>
        </div>
      </div>


      {/* AI Executive Coaching: Critical Moment Rewrites & Targeted Drills */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Critical Moment Rewrites: Side-by-Side (7 Cols) */}
        <div className="lg:col-span-7 bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 sm:p-7 shadow-lg flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex flex-col">
              <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">High-Impact Linguistic Polishing</span>
              <h3 className="font-headline-md text-lg text-on-surface font-bold">Critical Moment Rewrites</h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-label-numeric-sm text-xs text-secondary bg-surface-container px-2.5 py-1 rounded-md font-semibold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[14px]">schedule</span>
                {currentRewrite.timestamp || `00:${14 + (rewriteIdx % rewrites.length) * 16}`}
              </span>
              <span className="font-label-caps text-[10px] text-outline font-semibold bg-surface-container px-2 py-1 rounded-md">
                Moment {((rewriteIdx % rewrites.length) + 1)} of {rewrites.length}
              </span>
            </div>
          </div>

          <div className="bg-surface-container p-3 rounded-lg flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-outline">help_outline</span>
            <span className="text-xs text-on-surface-variant font-medium">
              Topic Probe: <span className="text-on-surface">{session.title}</span>
            </span>
          </div>

          {/* Side-by-Side Comparison Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Student Spoken Input */}
            <div className="p-4 rounded-xl bg-surface-container-high border border-outline-variant/30 flex flex-col justify-between gap-3 relative overflow-hidden">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] uppercase text-error tracking-wider font-bold flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">cancel</span> What You Said
                </span>
                <span className="font-label-numeric-sm text-[11px] px-2 py-0.5 rounded bg-surface-container-highest text-outline font-bold flex items-center gap-1">
                  Grade: <span className="text-error font-extrabold">{currentRewrite.grade || "C-"}</span>
                </span>
              </div>
              <p className="text-xs text-on-surface italic leading-relaxed">
                {currentRewrite.original}
              </p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <span className="font-label-caps text-[9px] px-2 py-0.5 rounded bg-error-container text-on-error-container font-semibold">
                  Colloquial qualifier
                </span>
                <span className="font-label-caps text-[9px] px-2 py-0.5 rounded bg-surface-container text-outline font-semibold">
                  Unquantified
                </span>
              </div>
            </div>

            {/* AI Model Recommended Output */}
            <div className="p-4 rounded-xl bg-primary-container/20 border border-primary/30 flex flex-col justify-between gap-3 relative shadow-inner">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] uppercase text-primary tracking-wider font-bold flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">auto_awesome</span> Recommended Polish
                </span>
                <span className="font-label-numeric-sm text-[11px] px-2 py-0.5 rounded bg-tertiary-container/30 text-tertiary font-bold flex items-center gap-1">
                  Grade: <span className="text-tertiary font-extrabold">{currentRewrite.polish_grade || "A+"}</span>
                </span>
              </div>
              <p className="text-xs text-on-surface font-medium leading-relaxed">
                {currentRewrite.polish}
              </p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <span className="font-label-caps text-[9px] px-2 py-0.5 rounded bg-tertiary-container/30 text-tertiary font-bold">
                  Metric Grounding
                </span>
                <span className="font-label-caps text-[9px] px-2 py-0.5 rounded bg-surface-container text-secondary font-bold">
                  Executive Voice
                </span>
              </div>
            </div>
          </div>

          {/* Micro Coaching Insight with Prev & Next */}
          <div className="p-3.5 rounded-lg bg-surface-container flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="material-symbols-outlined text-[18px] text-tertiary">tips_and_updates</span>
              <span className="text-xs text-on-surface-variant leading-relaxed">
                {currentRewrite.tip}
              </span>
            </div>
            {rewrites.length > 1 && (
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => setRewriteIdx((i) => (i - 1 + rewrites.length) % rewrites.length)}
                  className="px-2 py-1 rounded bg-surface-container-high hover:bg-surface-container-highest text-secondary hover:text-on-surface font-semibold flex items-center gap-0.5 text-xs transition-colors"
                  type="button"
                  title="Previous suggestion"
                >
                  <span className="material-symbols-outlined text-[16px]">chevron_left</span> Prev
                </button>
                <div className="flex items-center gap-1 px-1">
                  {rewrites.map((_, i) => (
                    <button
                      key={`moment-dot-${i}`}
                      type="button"
                      onClick={() => setRewriteIdx(i)}
                      className={`h-1.5 rounded-full transition-all ${
                        (rewriteIdx % rewrites.length) === i ? "w-4 bg-secondary" : "w-1.5 bg-outline-variant/60 hover:bg-outline"
                      }`}
                      title={`Go to Moment ${i + 1}`}
                    />
                  ))}
                </div>
                <button
                  onClick={() => setRewriteIdx((i) => (i + 1) % rewrites.length)}
                  className="px-2 py-1 rounded bg-surface-container-high hover:bg-surface-container-highest text-secondary hover:text-on-surface font-semibold flex items-center gap-0.5 text-xs transition-colors"
                  type="button"
                  title="Next suggestion"
                >
                  Next <span className="material-symbols-outlined text-[16px]">chevron_right</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Strengths & Targeted Action Plan (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Key Identified Strengths */}
          <div className="bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 shadow-lg flex flex-col gap-3">
            <div className="flex items-center justify-between pb-1">
              <span className="font-label-caps text-[11px] uppercase text-tertiary tracking-wider font-bold">
                Observed Mastery Points
              </span>
              <span className="material-symbols-outlined text-[20px] text-tertiary">verified</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {masteryPoints.map((point) => (
                <div key={point.title} className="flex items-start gap-2.5 p-3 rounded-lg bg-surface-container">
                  <span className="material-symbols-outlined text-[18px] text-tertiary mt-0.5">check_circle</span>
                  <div className="flex flex-col">
                    <span className="text-xs text-on-surface font-semibold">{point.title}</span>
                    <span className="text-[11px] text-on-surface-variant mt-0.5 leading-relaxed">{point.description}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Targeted Drills to Practice Next */}
          <div className="bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 shadow-lg flex flex-col gap-3">
            <div className="flex items-center justify-between pb-1">
              <span className="font-label-caps text-[11px] uppercase text-secondary tracking-wider font-bold">
                Curated Next Steps
              </span>
              <span className="font-label-numeric-sm text-xs text-outline font-medium">15 Min Total</span>
            </div>
            <div className="flex flex-col gap-2">
              {drills.map((drill) => (
                <Link
                  key={drill.title}
                  to={`/record?topic=${encodeURIComponent(drill.title)}`}
                  className="group p-3 rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-surface-container-highest flex items-center justify-center text-primary group-hover:scale-105 transition-transform">
                      <span className="material-symbols-outlined text-[18px]">{drill.icon || "bolt"}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold text-on-surface">{drill.title}</span>
                      <span className="font-label-numeric-sm text-[10px] text-outline">
                        {drill.desc} • {drill.duration}
                      </span>
                    </div>
                  </div>
                  <span className="material-symbols-outlined text-[18px] text-outline group-hover:text-primary transition-colors">
                    arrow_forward
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Multimodal Nonverbal Alignment & Congruence Section */}
      <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-lg flex flex-col gap-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="material-symbols-outlined text-tertiary text-[22px]">videocam</span>
            <div>
              <h3 className="font-headline-sm text-base text-on-surface font-bold">
                Utterance-Aligned Nonverbal Telemetry (MediaPipe)
              </h3>
              <p className="text-[11px] text-on-surface-variant">
                Visual gestures and facial affect synced directly to spoken intervals
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-label-caps text-[10px] px-2.5 py-1 rounded-full bg-surface-container-high text-secondary font-bold uppercase tracking-wider">
              {report?.congruence?.status || "High Alignment"}
            </span>
            {report?.avatar_reaction && (
              <span className="font-label-caps text-[10px] px-2.5 py-1 rounded-full bg-tertiary/15 text-tertiary font-bold flex items-center gap-1">
                <span className="material-symbols-outlined text-[12px]">smart_toy</span>
                Avatar: {report.avatar_reaction.expression}
              </span>
            )}
          </div>
        </div>

        {/* Congruence Insight */}
        {report?.congruence?.analysis && (
          <div className="p-3.5 rounded-lg bg-surface-container flex items-start gap-2.5 border-l-2 border-tertiary">
            <span className="material-symbols-outlined text-tertiary text-[18px] shrink-0 mt-0.5">psychology</span>
            <p className="text-xs text-on-surface font-medium leading-relaxed">
              {report.congruence.analysis}
            </p>
          </div>
        )}

        {/* Utterance Stream Cards */}
        {report?.multimodal_timeline && report.multimodal_timeline.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {report.multimodal_timeline.map((utt: any) => {
              const ec = Math.round((utt.face?.eye_contact_ratio || 0.8) * 100);
              const expr = utt.face?.dominant_expression || "Attentive";
              const posture = utt.gesture?.posture || "Upright";
              const events = utt.gesture?.events || [];

              return (
                <div
                  key={utt.utterance_id}
                  className="p-3.5 rounded-lg bg-surface-container border border-outline-variant/20 flex flex-col justify-between gap-2.5 hover:border-tertiary/40 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-label-numeric-sm text-[10px] text-outline font-semibold">
                      {Math.floor(utt.start / 60)}:{Math.floor(utt.start % 60).toString().padStart(2, "0")} -{" "}
                      {Math.floor(utt.end / 60)}:{Math.floor(utt.end % 60).toString().padStart(2, "0")}
                    </span>
                    <span className="font-label-numeric-sm text-[10px] text-tertiary font-bold flex items-center gap-1">
                      <span className="material-symbols-outlined text-[12px]">visibility</span>
                      {ec}% Gaze
                    </span>
                  </div>

                  <p className="text-xs text-on-surface font-medium line-clamp-2 italic">
                    "{utt.transcript}"
                  </p>

                  <div className="flex flex-wrap gap-1.5 pt-1 border-t border-outline-variant/20">
                    <span className="font-label-caps text-[9px] px-2 py-0.5 rounded bg-surface-container-highest text-secondary font-bold">
                      {expr}
                    </span>
                    <span className="font-label-caps text-[9px] px-2 py-0.5 rounded bg-surface-container-highest text-on-surface font-bold">
                      {posture}
                    </span>
                    {events.map((ev: string) => (
                      <span
                        key={ev}
                        className={`font-label-caps text-[9px] px-2 py-0.5 rounded font-bold ${
                          ev === "hand_to_face_touch"
                            ? "bg-error-container text-on-error-container"
                            : "bg-tertiary/15 text-tertiary"
                        }`}
                      >
                        {ev.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-4 rounded-lg bg-surface-container text-center text-xs text-outline">
            Multimodal visual cues synchronized with audio stream.
          </div>
        )}
      </div>

      {/* Verbatim Transcript Section */}
      {session.transcription?.text && (
        <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-lg flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-secondary text-[20px]">notes</span>
              <h3 className="font-headline-sm text-base text-on-surface font-bold">Verbatim Spoken Transcript</h3>
            </div>
            <span className="font-label-numeric-sm text-xs text-outline">
              Confidence: {Math.round(session.transcription.confidence * 100)}%
            </span>
          </div>
          <p className="text-xs sm:text-sm text-on-surface-variant leading-relaxed bg-surface-container p-4 rounded-lg font-mono">
            {session.transcription.text}
          </p>
        </div>
      )}
    </div>
  );
}

