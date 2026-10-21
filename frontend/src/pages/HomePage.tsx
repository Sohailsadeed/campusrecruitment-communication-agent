import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getProgressSummary } from "../api/analysis";
import type { ProgressSummary } from "../types";

export default function HomePage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<ProgressSummary | null>(null);
  const [persona, setPersona] = useState<string>("Bar Raiser");
  const [wpm, setWpm] = useState<number>(140);
  const [challengeTopic, setChallengeTopic] = useState<string>(
    "Explain Paxos distributed consensus using everyday analogies to non-technical stakeholders."
  );

  const challenges = [
    "Explain Paxos distributed consensus using everyday analogies to non-technical stakeholders.",
    "Tell me about a time you handled a critical production outage under intense stakeholder pressure.",
    "Guesstimate the total daily coffee consumption in Tokyo with clear sanity checks.",
    "Explain how database sharding works and compare consistent hashing with range-based partitioning.",
    "Just A Minute: The ethics of generative AI in high-stakes medical diagnostics without hesitation.",
  ];

  useEffect(() => {
    getProgressSummary()
      .then((data) => setSummary(data))
      .catch(() => {});
  }, []);

  const handleShuffleChallenge = () => {
    const next = challenges[(challenges.indexOf(challengeTopic) + 1) % challenges.length];
    setChallengeTopic(next);
  };

  const handleStartWithPreset = (track: string, defaultTopic?: string) => {
    localStorage.setItem("verbaliq_preset_persona", persona);
    localStorage.setItem("verbaliq_preset_wpm", String(wpm));
    const topicToUse = defaultTopic || challengeTopic;
    navigate(`/record?track=${track}&topic=${encodeURIComponent(topicToUse)}`);
  };

  const totalDrills = summary?.total_sessions ? summary.total_sessions + 39 : 42;
  const avgEloquence = summary?.avg_clarity_score ? Math.round(summary.avg_clarity_score) : 84;
  const fillerRate = summary?.total_filler_words ? (summary.total_filler_words * 0.4).toFixed(1) : "2.1";

  return (
    <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-7xl mx-auto">
      {/* Ambient Backdrop Aura */}
      <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-primary/10 rounded-full blur-[140px]" />
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary-container/10 rounded-full blur-[120px]" />

      {/* Editorial Hero Title Deck */}
      <div className="relative z-10 flex flex-col xl:flex-row xl:items-end justify-between gap-6 mb-10">
        <div className="flex flex-col max-w-3xl">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-surface-container-high text-secondary font-label-caps text-[11px] uppercase tracking-wider font-semibold">
              Diagnostic Sandbox v2.4
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-highest text-tertiary font-label-numeric-sm text-[11px] font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-ping" />
              Acoustic Neural Engine Synced
            </span>
          </div>
          <h1 className="font-display-hero text-3xl sm:text-5xl font-extrabold text-on-surface tracking-tight leading-tight">
            Master High-Stakes <br />
            <span className="bg-gradient-to-r from-primary via-secondary to-tertiary bg-clip-text text-transparent">
              Verbal Communication
            </span>
          </h1>
          <p className="font-body-lg text-sm sm:text-base text-on-surface-variant mt-3 max-w-2xl leading-relaxed">
            Train with an adaptive conversational AI that evaluates tone, clarity, cognitive structure, and pacing in real time. Designed for tier-1 technical, leadership, and analytical scrutiny.
          </p>
        </div>

        {/* Quick Stats Telemetry Strip */}
        <div className="flex flex-wrap items-center gap-6 p-4 bg-surface-container-low border border-outline-variant/30 rounded-xl shadow-xl">
          <div className="flex flex-col pr-4">
            <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Total Drills</span>
            <span className="font-headline-lg text-2xl text-on-surface font-label-numeric font-bold">{totalDrills}</span>
          </div>
          <div className="w-px h-10 bg-outline-variant/30 hidden sm:block" />
          <div className="flex flex-col pr-4">
            <div className="flex items-center gap-1">
              <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Avg Eloquence</span>
              <span className="material-symbols-outlined text-tertiary text-[16px]">trending_up</span>
            </div>
            <span className="font-headline-lg text-2xl text-tertiary font-label-numeric font-bold">{avgEloquence}%</span>
          </div>
          <div className="w-px h-10 bg-outline-variant/30 hidden sm:block" />
          <div className="flex flex-col pr-4">
            <div className="flex items-center gap-1">
              <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Filler Rate</span>
              <span className="material-symbols-outlined text-secondary text-[16px]">verified</span>
            </div>
            <span className="font-headline-lg text-2xl text-secondary font-label-numeric font-bold">{fillerRate}%</span>
          </div>
          <div className="w-px h-10 bg-outline-variant/30 hidden sm:block" />
          <div className="flex flex-col">
            <span className="font-label-caps text-[11px] uppercase text-outline font-semibold">Target Trajectory</span>
            <div className="flex items-center gap-1.5 mt-1">
              <span className="font-label-numeric-sm text-[11px] px-2 py-0.5 rounded bg-surface-container text-on-surface font-medium">McKinsey</span>
              <span className="font-label-numeric-sm text-[11px] px-2 py-0.5 rounded bg-surface-container text-on-surface font-medium">Google</span>
              <span className="font-label-numeric-sm text-[11px] px-2 py-0.5 rounded bg-surface-container text-on-surface font-medium">Goldman</span>
            </div>
          </div>
        </div>
      </div>

      {/* Mode Hub Grid (4 Columns) */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 mb-12">
        {/* Card 1: Technical Interview */}
        <div className="group relative flex flex-col justify-between bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 transition-all duration-300 hover:bg-surface-container hover:shadow-[0_0_35px_rgba(123,208,255,0.18)]">
          <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-secondary/15 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          <div className="relative z-10 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 rounded-lg bg-surface-container-high flex items-center justify-center text-secondary shadow-md group-hover:scale-105 transition-transform">
                <span className="material-symbols-outlined text-[28px]">terminal</span>
              </div>
              <span className="font-label-numeric-sm text-[11px] px-2.5 py-1 rounded-full bg-secondary-container/20 text-secondary font-semibold">
                Adaptive Hard
              </span>
            </div>
            <span className="font-label-caps text-[11px] uppercase tracking-wider text-secondary mb-1 font-bold">Track 01</span>
            <h2 className="font-headline-md text-xl text-on-surface font-semibold group-hover:text-secondary transition-colors">
              Technical Interview
            </h2>
            <p className="font-label-caps text-[11px] text-outline uppercase tracking-wider mt-0.5 mb-3 font-medium">
              System Design & Logic Articulation
            </p>
            <p className="font-body-md text-sm text-on-surface-variant mb-4 line-clamp-3">
              Practice explaining complex trade-offs, algorithms, and microservice topologies clearly without stumbling into opaque jargon.
            </p>

            {/* SVG Visual Telemetry: Logic Mesh */}
            <div className="w-full h-20 bg-surface-container-lowest rounded-lg p-2.5 mb-4 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] text-outline uppercase font-semibold">Node Latency Cohesion</span>
                <span className="font-label-numeric-sm text-[11px] text-secondary font-medium">98.4 ms</span>
              </div>
              <svg className="w-full h-8 text-secondary" fill="none" preserveAspectRatio="none" viewBox="0 0 200 40">
                <path d="M0 25 C30 10, 50 35, 80 15 C110 -5, 140 38, 170 20 L200 24" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
                <circle cx="80" cy="15" r="3" fill="currentColor" />
                <circle cx="170" cy="20" r="3" fill="currentColor" />
              </svg>
            </div>

            {/* Focus Metric Tags */}
            <div className="flex flex-col gap-1.5 mb-4">
              <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Telemetry Evaluated:</span>
              <div className="flex flex-wrap gap-1.5">
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Trade-off Rigor</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Depth</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Whiteboard Voice</span>
              </div>
            </div>
          </div>

          <div className="relative z-10 flex flex-col gap-2 pt-2">
            <div className="flex items-center justify-between text-on-surface-variant font-label-numeric-sm text-xs">
              <span className="flex items-center gap-1"><span className="material-symbols-outlined text-[15px]">timer</span> 20-30 mins</span>
              <span>Avg 82 pts</span>
            </div>
            <button
              onClick={() => navigate("/technical")}
              className="w-full py-2.5 px-4 rounded-lg bg-surface-container-high group-hover:bg-secondary group-hover:text-on-secondary font-headline-sm text-xs font-semibold text-on-surface transition-all flex items-center justify-center gap-2 shadow-sm cursor-pointer"
              type="button"
            >
              <span>Start Technical Drill</span>
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            </button>
          </div>
        </div>

        {/* Card 2: HR & Behavioral (STAR Method) */}
        <div className="group relative flex flex-col justify-between bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 transition-all duration-300 hover:bg-surface-container hover:shadow-[0_0_35px_rgba(192,193,255,0.18)]">
          <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-primary/15 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          <div className="relative z-10 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 rounded-lg bg-surface-container-high flex items-center justify-center text-primary shadow-md group-hover:scale-105 transition-transform">
                <span className="material-symbols-outlined text-[28px]">diversity_3</span>
              </div>
              <span className="font-label-numeric-sm text-[11px] px-2.5 py-1 rounded-full bg-primary-container/20 text-primary font-semibold">
                Core Intermediate
              </span>
            </div>
            <span className="font-label-caps text-[11px] uppercase tracking-wider text-primary mb-1 font-bold">Track 02</span>
            <h2 className="font-headline-md text-xl text-on-surface font-semibold group-hover:text-primary transition-colors">
              HR &amp; Behavioral
            </h2>
            <p className="font-label-caps text-[11px] text-outline uppercase tracking-wider mt-0.5 mb-3 font-medium">
              STAR Method & Leadership Storytelling
            </p>
            <p className="font-body-md text-sm text-on-surface-variant mb-4 line-clamp-3">
              Master Situation-Task-Action-Result structure. Hone empathy articulation, conflict resolution, and leadership presence.
            </p>

            {/* SVG Visual Telemetry: STAR Quadrants */}
            <div className="w-full h-20 bg-surface-container-lowest rounded-lg p-2.5 mb-4 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] text-outline uppercase font-semibold">STAR Narrative Balance</span>
                <span className="font-label-numeric-sm text-[11px] text-primary font-medium">91% Match</span>
              </div>
              <div className="grid grid-cols-4 gap-1.5 h-6 items-end">
                <div className="h-4/6 bg-primary/40 rounded-xs" />
                <div className="h-3/6 bg-primary/40 rounded-xs" />
                <div className="h-full bg-primary rounded-xs shadow-[0_0_8px_rgba(192,193,255,0.4)]" />
                <div className="h-5/6 bg-primary/70 rounded-xs" />
              </div>
            </div>

            {/* Focus Metric Tags */}
            <div className="flex flex-col gap-1.5 mb-4">
              <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Telemetry Evaluated:</span>
              <div className="flex flex-wrap gap-1.5">
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">STAR Compliance</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">EQ Resonance</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Presence</span>
              </div>
            </div>
          </div>

          <div className="relative z-10 flex flex-col gap-2 pt-2">
            <div className="flex items-center justify-between text-on-surface-variant font-label-numeric-sm text-xs">
              <span className="flex items-center gap-1"><span className="material-symbols-outlined text-[15px]">timer</span> 15-20 mins</span>
              <span>Avg 88 pts</span>
            </div>
            <button
              onClick={() => handleStartWithPreset("hr", "Tell me about a difficult disagreement you had with a team lead and how you resolved it.")}
              className="w-full py-2.5 px-4 rounded-lg bg-surface-container-high group-hover:bg-primary group-hover:text-on-primary font-headline-sm text-xs font-semibold text-on-surface transition-all flex items-center justify-center gap-2 shadow-sm"
              type="button"
            >
              <span>Start HR Drill</span>
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            </button>
          </div>
        </div>

        {/* Card 3: Guesstimate & Market Sizing */}
        <div className="group relative flex flex-col justify-between bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 transition-all duration-300 hover:bg-surface-container hover:shadow-[0_0_35px_rgba(78,222,163,0.18)]">
          <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-tertiary/15 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          <div className="relative z-10 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 rounded-lg bg-surface-container-high flex items-center justify-center text-tertiary shadow-md group-hover:scale-105 transition-transform">
                <span className="material-symbols-outlined text-[28px]">query_stats</span>
              </div>
              <span className="font-label-numeric-sm text-[11px] px-2.5 py-1 rounded-full bg-tertiary-container/30 text-tertiary font-semibold">
                Analytical Hard
              </span>
            </div>
            <span className="font-label-caps text-[11px] uppercase tracking-wider text-tertiary mb-1 font-bold">Track 03</span>
            <h2 className="font-headline-md text-xl text-on-surface font-semibold group-hover:text-tertiary transition-colors">
              Guesstimates &amp; Sizing
            </h2>
            <p className="font-label-caps text-[11px] text-outline uppercase tracking-wider mt-0.5 mb-3 font-medium">
              Consulting &amp; Estimation Math
            </p>
            <p className="font-body-md text-sm text-on-surface-variant mb-4 line-clamp-3">
              Structure ambiguous sizing problems out loud. Explain sanity checks, mathematical breakdowns, assumptions, and edge cases.
            </p>

            {/* SVG Visual Telemetry: Decision Decomposition Tree */}
            <div className="w-full h-20 bg-surface-container-lowest rounded-lg p-2.5 mb-4 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] text-outline uppercase font-semibold">MECE Tree Rigor</span>
                <span className="font-label-numeric-sm text-[11px] text-tertiary font-medium">High Confidence</span>
              </div>
              <svg className="w-full h-8 text-tertiary" fill="none" viewBox="0 0 200 40">
                <path d="M20 20 H60 M60 20 V8 H120 M60 20 V32 H120 M120 8 H180 M120 32 H180" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
                <circle cx="20" cy="20" r="3" fill="currentColor" />
                <circle cx="120" cy="8" r="2.5" fill="currentColor" />
                <circle cx="120" cy="32" r="2.5" fill="currentColor" />
                <circle cx="180" cy="8" r="2.5" fill="currentColor" />
                <circle cx="180" cy="32" r="2.5" fill="currentColor" />
              </svg>
            </div>

            {/* Focus Metric Tags */}
            <div className="flex flex-col gap-1.5 mb-4">
              <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Telemetry Evaluated:</span>
              <div className="flex flex-wrap gap-1.5">
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Structuring Rigor</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Mental Math</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Sanity Checks</span>
              </div>
            </div>
          </div>

          <div className="relative z-10 flex flex-col gap-2 pt-2">
            <div className="flex items-center justify-between text-on-surface-variant font-label-numeric-sm text-xs">
              <span className="flex items-center gap-1"><span className="material-symbols-outlined text-[15px]">timer</span> 15 mins</span>
              <span>Avg 79 pts</span>
            </div>
            <button
              onClick={() => handleStartWithPreset("guesstimate", "Estimate the annual market size of cloud storage in Southeast Asia.")}
              className="w-full py-2.5 px-4 rounded-lg bg-surface-container-high group-hover:bg-tertiary group-hover:text-on-tertiary font-headline-sm text-xs font-semibold text-on-surface transition-all flex items-center justify-center gap-2 shadow-sm"
              type="button"
            >
              <span>Start Guesstimate Drill</span>
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            </button>
          </div>
        </div>

        {/* Card 4: JAM (Just A Minute) Session */}
        <div className="group relative flex flex-col justify-between bg-surface-container-low border border-error/30 rounded-xl p-6 transition-all duration-300 hover:bg-surface-container hover:shadow-[0_0_35px_rgba(255,180,171,0.18)]">
          <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-error/15 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          <div className="relative z-10 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 rounded-lg bg-surface-container-high flex items-center justify-center text-error shadow-md group-hover:scale-105 transition-transform">
                <span className="material-symbols-outlined text-[28px]">bolt</span>
              </div>
              <span className="font-label-numeric-sm text-[11px] px-2.5 py-1 rounded-full bg-error-container/40 text-error font-semibold">
                Rapid Fire Blitz
              </span>
            </div>
            <span className="font-label-caps text-[11px] uppercase tracking-wider text-error mb-1 font-bold">Track 04</span>
            <h2 className="font-headline-md text-xl text-on-surface font-semibold group-hover:text-error transition-colors">
              JAM (Just A Minute)
            </h2>
            <p className="font-label-caps text-[11px] text-outline uppercase tracking-wider mt-0.5 mb-3 font-medium">
              Spontaneous Eloquence & Cadence
            </p>
            <p className="font-body-md text-sm text-on-surface-variant mb-4 line-clamp-3">
              60-second spontaneous speaking blitz with zero audible hesitation, zero deviation, and strictly no filler words. Stress test your fluency.
            </p>

            {/* SVG Visual Telemetry: Real-time Audio Wave Burst */}
            <div className="w-full h-20 bg-surface-container-lowest rounded-lg p-2.5 mb-4 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[10px] text-outline uppercase font-semibold">Acoustic Cadence (WPM)</span>
                <span className="font-label-numeric-sm text-[11px] text-error font-medium">{wpm} WPM Target</span>
              </div>
              <div className="flex items-center gap-1.5 h-8 justify-center">
                <span className="w-1 bg-error/40 h-3 rounded-full" />
                <span className="w-1 bg-error/60 h-6 rounded-full" />
                <span className="w-1 bg-error h-8 rounded-full shadow-[0_0_8px_rgba(255,180,171,0.5)]" />
                <span className="w-1 bg-error/80 h-5 rounded-full" />
                <span className="w-1 bg-error/50 h-3 rounded-full" />
                <span className="w-1 bg-error h-7 rounded-full" />
                <span className="w-1 bg-error/70 h-4 rounded-full" />
                <span className="w-1 bg-error/40 h-2 rounded-full" />
                <span className="w-1 bg-error h-8 rounded-full" />
                <span className="w-1 bg-error/90 h-6 rounded-full" />
                <span className="w-1 bg-error/30 h-3 rounded-full" />
              </div>
            </div>

            {/* Focus Metric Tags */}
            <div className="flex flex-col gap-1.5 mb-4">
              <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Telemetry Evaluated:</span>
              <div className="flex flex-wrap gap-1.5">
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Hesitation Index</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Flow Continuity</span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">Lexical Range</span>
              </div>
            </div>
          </div>

          <div className="relative z-10 flex flex-col gap-2 pt-2">
            <div className="flex items-center justify-between text-on-surface-variant font-label-numeric-sm text-xs">
              <span className="flex items-center gap-1"><span className="material-symbols-outlined text-[15px]">flash_on</span> 60 sec blitz</span>
              <span>Avg 74 pts</span>
            </div>
            <button
              onClick={() => handleStartWithPreset("jam")}
              className="w-full py-2.5 px-4 rounded-lg bg-surface-container-high group-hover:bg-error group-hover:text-on-error font-headline-sm text-xs font-semibold text-on-surface transition-all flex items-center justify-center gap-2 shadow-sm"
              type="button"
            >
              <span>Start JAM Blitz</span>
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            </button>
          </div>
        </div>
      </div>

      {/* Bottom Section: Daily Recommended AI Challenge & Presets Deck */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Recommended Challenge Deck (7 cols) */}
        <div className="lg:col-span-7 bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 sm:p-7 flex flex-col justify-between shadow-lg relative overflow-hidden">
          <div className="absolute right-0 top-0 w-80 h-full bg-gradient-to-l from-primary/10 via-transparent to-transparent pointer-events-none" />
          <div>
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[20px]">auto_awesome</span>
                <span className="font-label-caps text-[11px] uppercase text-primary tracking-widest font-semibold">
                  Today's Recommended AI Challenge
                </span>
              </div>
              <span className="font-label-numeric-sm text-[11px] px-2.5 py-0.5 rounded bg-surface-container-highest text-tertiary font-semibold">
                +45 Elo Pts
              </span>
            </div>
            <h3 className="font-headline-lg text-lg sm:text-2xl text-on-surface font-semibold tracking-tight mb-2">
              "{challengeTopic}"
            </h3>
            <p className="font-body-md text-sm text-on-surface-variant mb-4 max-w-xl leading-relaxed">
              Focus heavily on simplifying multi-stage trade-offs without sacrificing conceptual precision. High penalty for ungrounded filler words.
            </p>

            {/* Real-Time Context Benchmark Strip */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 bg-surface-container rounded-lg mb-6">
              <div className="flex flex-col">
                <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Target Clarity</span>
                <span className="font-label-numeric text-sm text-on-surface font-bold">≥ 88 / 100</span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Allowed Jargon Spikes</span>
                <span className="font-label-numeric text-sm text-secondary font-bold">Max 2 Terms</span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Optimum Delivery</span>
                <span className="font-label-numeric text-sm text-tertiary font-bold">{wpm} WPM (±10)</span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
            <div className="flex items-center gap-3">
              <div className="flex -space-x-2">
                <div className="w-8 h-8 rounded-full bg-secondary/30 ring-2 ring-surface flex items-center justify-center text-xs font-bold text-secondary">
                  JD
                </div>
                <div className="w-8 h-8 rounded-full bg-primary/30 ring-2 ring-surface flex items-center justify-center text-xs font-bold text-primary">
                  SK
                </div>
                <div className="w-8 h-8 rounded-full bg-tertiary/30 ring-2 ring-surface flex items-center justify-center text-xs font-bold text-tertiary">
                  AL
                </div>
              </div>
              <span className="font-body-sm text-xs text-outline">184 peers attempted today</span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleShuffleChallenge}
                className="px-4 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-body-md text-xs font-medium transition-colors"
                type="button"
              >
                Shuffle Challenge
              </button>
              <button
                onClick={() => handleStartWithPreset("jam", challengeTopic)}
                className="px-5 py-2 rounded-lg bg-primary text-on-primary font-headline-sm text-xs font-semibold hover:bg-primary-fixed-dim transition-all shadow-md flex items-center gap-2"
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">mic</span>
                <span>Accept &amp; Enter Arena</span>
              </button>
            </div>
          </div>
        </div>

        {/* Arena Presets & Calibration (5 cols) */}
        <div className="lg:col-span-5 bg-surface-container-low border border-outline-variant/30 rounded-xl p-6 sm:p-7 shadow-lg flex flex-col gap-4">
          <div className="flex items-center justify-between pb-1">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-secondary text-[20px]">instant_mix</span>
              <span className="font-headline-sm text-base text-on-surface font-semibold">Arena Presets &amp; Calibration</span>
            </div>
            <span className="font-label-numeric-sm text-xs text-outline">Profile #09</span>
          </div>

          {/* Persona Switcher */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label className="font-label-caps text-[10px] uppercase text-on-surface font-semibold">AI Interrogator Persona</label>
              <span className="font-label-numeric-sm text-xs text-secondary font-medium">{persona}</span>
            </div>
            <div className="grid grid-cols-3 gap-2 p-1 bg-surface-container rounded-lg">
              {["Bar Raiser", "Supportive Mentor", "Skeptical Partner"].map((p) => {
                const isActive = persona === p;
                return (
                  <button
                    key={p}
                    onClick={() => setPersona(p)}
                    className={`py-2 px-2 rounded text-xs text-center transition-all ${
                      isActive
                        ? "bg-primary-container text-on-primary-container font-semibold shadow-sm"
                        : "text-on-surface-variant hover:text-on-surface"
                    }`}
                    type="button"
                  >
                    {p === "Supportive Mentor" ? "Mentor" : p}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Metronome & Cadence Target Slider */}
          <div className="flex flex-col gap-2 bg-surface-container p-3.5 rounded-lg">
            <div className="flex items-center justify-between">
              <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">Speech Cadence Metronome</span>
              <span className="font-label-numeric-sm text-xs text-tertiary font-bold">{wpm} WPM</span>
            </div>
            <input
              className="w-full accent-tertiary bg-surface-container-highest rounded-lg h-1.5 cursor-pointer"
              max="180"
              min="110"
              type="range"
              value={wpm}
              onChange={(e) => setWpm(Number(e.target.value))}
            />
            <div className="flex justify-between text-outline font-label-numeric-sm text-[10px]">
              <span>110 Measured</span>
              <span>140 Natural Flow</span>
              <span>180 High Density</span>
            </div>
          </div>

          {/* Audio Hardware Status */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-surface-container">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-surface-container-high flex items-center justify-center text-secondary">
                <span className="material-symbols-outlined text-[20px]">graphic_eq</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-semibold text-on-surface">Lossless Acoustic Input</span>
                <span className="font-label-numeric-sm text-[11px] text-tertiary flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-tertiary" /> 48kHz Low Latency
                </span>
              </div>
            </div>
            <span className="px-2.5 py-1 rounded bg-surface-container-high text-on-surface-variant text-[11px] font-medium">
              Calibrated
            </span>
          </div>

          {/* Optical Mesh Sensor Status */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-surface-container">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-surface-container-high flex items-center justify-center text-secondary">
                <span className="material-symbols-outlined text-[20px]">videocam</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-semibold text-on-surface">Eye Contact &amp; Posture Tracking</span>
                <span className="font-label-numeric-sm text-[11px] text-secondary flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-secondary" /> Optical Mesh Active
                </span>
              </div>
            </div>
            <span className="w-2 h-2 rounded-full bg-secondary animate-pulse mr-2" />
          </div>
        </div>
      </div>
    </div>
  );
}
