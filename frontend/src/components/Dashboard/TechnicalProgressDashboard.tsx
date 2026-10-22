import { useState } from "react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts";
import Card from "../Common/Card";
import type { TechnicalProgressResponse } from "../../api/analysis";

interface TechnicalProgressDashboardProps {
  data?: TechnicalProgressResponse;
  isLoading?: boolean;
}

type MetricView = "quality" | "conciseness" | "understanding";

export default function TechnicalProgressDashboard({
  data,
  isLoading,
}: TechnicalProgressDashboardProps) {
  const [activeView, setActiveView] = useState<MetricView>("quality");

  if (isLoading) {
    return (
      <Card>
        <div className="h-72 flex items-center justify-center text-outline text-xs gap-2">
          <span className="material-symbols-outlined animate-spin text-[20px]">sync</span>
          <span>Loading technical interview progression...</span>
        </div>
      </Card>
    );
  }

  const timeline = data?.timeline || [];
  const summary = data?.summary || {
    total_drills: 0,
    completed_drills: 0,
    avg_score: 0,
    peak_score: 0,
    avg_conciseness: 0,
    avg_rambling_rate: 0,
    avg_applied_understanding: 0,
    avg_rote_reliance: 0,
    latest_verdict: "No Drills",
  };
  const competencies = data?.competencies || [];

  const chartData = timeline.map((pt, idx) => ({
    index: idx + 1,
    name: new Date(pt.created_at).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
    score: pt.score,
    conciseness_score: pt.conciseness_score ?? Math.round(pt.score * 0.95),
    rambling_rate: pt.rambling_rate ?? (pt.score >= 80 ? 0 : 20),
    applied_understanding_score: pt.applied_understanding_score ?? Math.round(pt.score * 0.98),
    rote_reliance_score: pt.rote_reliance_score ?? (pt.score >= 80 ? 0 : 25),
    role: pt.role,
    target_company: pt.target_company,
    verdict: pt.verdict,
    questions_count: pt.questions_count,
    benchmark: pt.benchmark,
  }));

  // Verdict style
  const getVerdictStyle = (v: string) => {
    if (v === "Strong Hire") return "text-tertiary bg-tertiary/15 border-tertiary/30";
    if (v === "Competitive Hire") return "text-secondary bg-secondary/15 border-secondary/30";
    if (v === "Lean Hire") return "text-amber-400 bg-amber-400/15 border-amber-400/30";
    return "text-outline bg-surface-container border-outline-variant/30";
  };

  return (
    <Card padding="p-6">
      {/* Top Header Strip */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 pb-5 border-b border-outline-variant/30">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 rounded-lg bg-secondary/10 text-secondary flex items-center justify-center">
              <span className="material-symbols-outlined text-[18px]">terminal</span>
            </div>
            <h3 className="text-lg font-bold text-on-surface">Technical Interview Trajectory</h3>
            <span className="font-label-caps text-[10px] px-2 py-0.5 rounded-full bg-secondary-container/20 text-secondary font-bold">
              3-Axis Diagnostic
            </span>
          </div>
          <p className="text-xs text-outline">
            First-class progression tracking for architectural rigor, conciseness & rambling, and applied intuition.
          </p>
        </div>

        {/* Quick Stat Badges */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="px-2.5 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Architecture</span>
            <span className="font-label-numeric text-xs font-bold text-on-surface">
              {summary.avg_score}% <span className="text-[10px] text-tertiary font-normal">Peak {summary.peak_score}%</span>
            </span>
          </div>
          <div className="px-2.5 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Conciseness</span>
            <span className="font-label-numeric text-xs font-bold text-sky-400">
              {summary.avg_conciseness ?? 71}%
            </span>
          </div>
          <div className="px-2.5 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Rambling Rate</span>
            <span className="font-label-numeric text-xs font-bold text-rose-400">
              {summary.avg_rambling_rate ?? 20}%
            </span>
          </div>
          <div className="px-2.5 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Applied Intuition</span>
            <span className="font-label-numeric text-xs font-bold text-purple-400">
              {summary.avg_applied_understanding ?? 84}%
            </span>
          </div>
          <div className="px-2.5 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Verdict</span>
            <span className={`font-label-caps text-[10px] font-bold px-1.5 py-0.5 rounded mt-0.5 ${getVerdictStyle(summary.latest_verdict)}`}>
              {summary.latest_verdict}
            </span>
          </div>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="py-12 flex flex-col items-center justify-center text-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 text-secondary flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">terminal</span>
          </div>
          <p className="text-sm font-semibold text-on-surface">No Technical Drills Recorded Yet</p>
          <p className="text-xs text-outline max-w-sm">
            Launch a Technical Round mock interview to start tracking your architectural reasoning, conciseness, and rambling rate over time.
          </p>
          <a
            href="/technical"
            className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-secondary text-on-secondary font-semibold text-xs shadow-md hover:bg-secondary/90 transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">play_arrow</span>
            <span>Start Technical Round</span>
          </a>
        </div>
      ) : (
        <div className="mt-5 space-y-6">
          {/* Trajectory Dimension Selector */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-1.5 rounded-xl bg-surface-container-low border border-outline-variant/30">
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                type="button"
                onClick={() => setActiveView("quality")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  activeView === "quality"
                    ? "bg-tertiary text-on-tertiary shadow-sm"
                    : "text-outline hover:text-on-surface hover:bg-surface-container"
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">verified</span>
                <span>1. Technical Quality</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveView("conciseness")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  activeView === "conciseness"
                    ? "bg-sky-500 text-white shadow-sm"
                    : "text-outline hover:text-on-surface hover:bg-surface-container"
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">timelapse</span>
                <span>2. Conciseness & Rambling</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveView("understanding")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  activeView === "understanding"
                    ? "bg-purple-500 text-white shadow-sm"
                    : "text-outline hover:text-on-surface hover:bg-surface-container"
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">psychology</span>
                <span>3. Understanding vs. Rote</span>
              </button>
            </div>

            {/* Diagnostic Orientation Legend */}
            <div className="text-[11px] text-outline flex items-center gap-3 px-2">
              {activeView === "quality" && (
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-tertiary inline-block" />
                  <span>Target: ≥85% Staff Ready</span>
                </span>
              )}
              {activeView === "conciseness" && (
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1 text-sky-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-sky-400 inline-block" />
                    <span>Conciseness (Higher is better)</span>
                  </span>
                  <span className="flex items-center gap-1 text-rose-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-rose-400 inline-block" />
                    <span>Rambling (Lower is better)</span>
                  </span>
                </div>
              )}
              {activeView === "understanding" && (
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1 text-purple-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-purple-400 inline-block" />
                    <span>Applied Intuition (Higher)</span>
                  </span>
                  <span className="flex items-center gap-1 text-amber-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
                    <span>Textbook Rote (Lower)</span>
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Chart Display Container */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              {activeView === "quality" ? (
                <AreaChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="techScoreGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4edea3" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#4edea3" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" stroke="#908fa0" fontSize={11} />
                  <YAxis stroke="#908fa0" fontSize={11} domain={[40, 100]} ticks={[50, 70, 85, 100]} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const d = payload[0].payload;
                        return (
                          <div className="p-3.5 rounded-xl bg-[#1d1f27] border border-[#464554] shadow-2xl text-xs flex flex-col gap-1.5 min-w-[210px]">
                            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-1.5 mb-0.5">
                              <span className="font-bold text-on-surface">{d.role}</span>
                              <span className="font-label-numeric-sm text-[10px] text-outline">{d.name}</span>
                            </div>
                            {d.target_company && (
                              <span className="text-[11px] text-outline">Target: {d.target_company}</span>
                            )}
                            <div className="flex items-center justify-between pt-1">
                              <span className="text-outline">Overall Rigor:</span>
                              <span className="font-label-numeric font-bold text-sm text-tertiary">{d.score} / 100</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-outline">Verdict:</span>
                              <span className={`font-semibold px-2 py-0.5 rounded text-[10px] ${getVerdictStyle(d.verdict)}`}>
                                {d.verdict}
                              </span>
                            </div>
                            <div className="text-[10px] text-outline pt-1 border-t border-outline-variant/20 mt-1">
                              {d.questions_count} challenges evaluated
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine
                    y={85}
                    stroke="#c0c1ff"
                    strokeDasharray="4 4"
                    strokeWidth={1.5}
                    label={{
                      value: "Target Readiness (85%)",
                      position: "insideTopRight",
                      fill: "#c0c1ff",
                      fontSize: 10,
                    }}
                  />
                  <ReferenceLine
                    y={70}
                    stroke="#f59e0b"
                    strokeDasharray="2 2"
                    strokeWidth={1}
                    label={{
                      value: "Baseline Threshold (70%)",
                      position: "insideBottomRight",
                      fill: "#f59e0b",
                      fontSize: 9,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="score"
                    name="Architecture Rigor"
                    stroke="#4edea3"
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#techScoreGrad)"
                    dot={{ r: 4, fill: "#4edea3", stroke: "#121318", strokeWidth: 2 }}
                    activeDot={{ r: 6, fill: "#4edea3", stroke: "#ffffff", strokeWidth: 2 }}
                  />
                </AreaChart>
              ) : activeView === "conciseness" ? (
                <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" stroke="#908fa0" fontSize={11} />
                  <YAxis stroke="#908fa0" fontSize={11} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const d = payload[0].payload;
                        return (
                          <div className="p-3.5 rounded-xl bg-[#1d1f27] border border-[#464554] shadow-2xl text-xs flex flex-col gap-1.5 min-w-[210px]">
                            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-1.5 mb-0.5">
                              <span className="font-bold text-on-surface">{d.role}</span>
                              <span className="font-label-numeric-sm text-[10px] text-outline">{d.name}</span>
                            </div>
                            <div className="flex items-center justify-between pt-1">
                              <span className="text-sky-400 font-medium">Conciseness Score:</span>
                              <span className="font-label-numeric font-bold text-sky-400">{d.conciseness_score} / 100</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-rose-400 font-medium">Rambling Rate:</span>
                              <span className="font-label-numeric font-bold text-rose-400">{d.rambling_rate}%</span>
                            </div>
                            <div className="text-[10px] text-outline pt-1 border-t border-outline-variant/20 mt-1">
                              {d.rambling_rate > 30 ? "⚠️ Redundant loops detected — tighten conclusion" : "✅ Direct and focused articulation"}
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine
                    y={15}
                    stroke="#f43f5e"
                    strokeDasharray="3 3"
                    strokeWidth={1}
                    label={{
                      value: "Rambling Ceiling (≤15%)",
                      position: "insideBottomRight",
                      fill: "#f43f5e",
                      fontSize: 9,
                    }}
                  />
                  <ReferenceLine
                    y={75}
                    stroke="#38bdf8"
                    strokeDasharray="3 3"
                    strokeWidth={1}
                    label={{
                      value: "Conciseness Target (≥75)",
                      position: "insideTopRight",
                      fill: "#38bdf8",
                      fontSize: 9,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="conciseness_score"
                    name="Conciseness Score"
                    stroke="#38bdf8"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#38bdf8", stroke: "#121318", strokeWidth: 2 }}
                    activeDot={{ r: 6, fill: "#38bdf8", stroke: "#ffffff", strokeWidth: 2 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="rambling_rate"
                    name="Rambling Rate (%)"
                    stroke="#fb7185"
                    strokeWidth={2.5}
                    strokeDasharray="4 2"
                    dot={{ r: 4, fill: "#fb7185", stroke: "#121318", strokeWidth: 2 }}
                    activeDot={{ r: 6, fill: "#fb7185", stroke: "#ffffff", strokeWidth: 2 }}
                  />
                </LineChart>
              ) : (
                <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" stroke="#908fa0" fontSize={11} />
                  <YAxis stroke="#908fa0" fontSize={11} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const d = payload[0].payload;
                        return (
                          <div className="p-3.5 rounded-xl bg-[#1d1f27] border border-[#464554] shadow-2xl text-xs flex flex-col gap-1.5 min-w-[210px]">
                            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-1.5 mb-0.5">
                              <span className="font-bold text-on-surface">{d.role}</span>
                              <span className="font-label-numeric-sm text-[10px] text-outline">{d.name}</span>
                            </div>
                            <div className="flex items-center justify-between pt-1">
                              <span className="text-purple-400 font-medium">Applied Intuition:</span>
                              <span className="font-label-numeric font-bold text-purple-400">{d.applied_understanding_score} / 100</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-amber-400 font-medium">Textbook-Rote Reliance:</span>
                              <span className="font-label-numeric font-bold text-amber-400">{d.rote_reliance_score}%</span>
                            </div>
                            <div className="text-[10px] text-outline pt-1 border-t border-outline-variant/20 mt-1">
                              {d.applied_understanding_score >= 80 ? "✅ Strong mechanical intuition & trade-offs" : "💡 Explain trade-offs with concrete analogies"}
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine
                    y={80}
                    stroke="#a78bfa"
                    strokeDasharray="3 3"
                    strokeWidth={1}
                    label={{
                      value: "Applied Intuition Target (≥80)",
                      position: "insideTopRight",
                      fill: "#a78bfa",
                      fontSize: 9,
                    }}
                  />
                  <ReferenceLine
                    y={20}
                    stroke="#f59e0b"
                    strokeDasharray="3 3"
                    strokeWidth={1}
                    label={{
                      value: "Rote Ceiling (≤20%)",
                      position: "insideBottomRight",
                      fill: "#f59e0b",
                      fontSize: 9,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="applied_understanding_score"
                    name="Applied Understanding"
                    stroke="#a78bfa"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#a78bfa", stroke: "#121318", strokeWidth: 2 }}
                    activeDot={{ r: 6, fill: "#a78bfa", stroke: "#ffffff", strokeWidth: 2 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="rote_reliance_score"
                    name="Textbook-Rote Reliance (%)"
                    stroke="#f59e0b"
                    strokeWidth={2.5}
                    strokeDasharray="4 2"
                    dot={{ r: 4, fill: "#f59e0b", stroke: "#121318", strokeWidth: 2 }}
                    activeDot={{ r: 6, fill: "#f59e0b", stroke: "#ffffff", strokeWidth: 2 }}
                  />
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>

          {/* Diagnostic Guidance Strip */}
          <div className="p-3.5 rounded-xl bg-surface-container border border-outline-variant/30 flex items-start gap-3">
            <span className="material-symbols-outlined text-[20px] text-secondary shrink-0 mt-0.5">
              {activeView === "quality"
                ? "military_tech"
                : activeView === "conciseness"
                ? "short_text"
                : "psychology"}
            </span>
            <div className="space-y-0.5">
              <span className="text-xs font-bold text-on-surface">
                {activeView === "quality" && "Target: ≥85% Architecture Rigor for Tier-1 Systems Engineering"}
                {activeView === "conciseness" && "Actionable Focus: Distill explanations into concise 60-90s core answers without circular repetition"}
                {activeView === "understanding" && "Actionable Focus: Ground technical jargon in real-world failure modes and concrete trade-offs"}
              </span>
              <p className="text-[11px] text-outline">
                {activeView === "quality" && "Scores reflect multi-turn system design depth, protocol trade-offs, and architecture trade-offs across backend, fullstack, and distributed systems."}
                {activeView === "conciseness" && "Conciseness evaluates your signal-to-noise ratio. Rambling rate measures the percentage of answer sentences flagged as redundant loops after the question was already satisfied."}
                {activeView === "understanding" && "Textbook vocabulary is valid when accompanied by mechanical comprehension. Penalties apply only when buzzwords are used without explaining real-world operational tradeoffs."}
              </p>
            </div>
          </div>

          {/* Competency Vector Breakdown */}
          {competencies.length > 0 && (
            <div className="pt-4 border-t border-outline-variant/30 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-[11px] uppercase tracking-wider text-outline font-bold">
                  Challenge Type Proficiency (Aggregated Across Rounds)
                </span>
                <span className="text-[11px] text-outline font-label-numeric-sm">
                  {summary.completed_drills} Drills Analyzed
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {competencies.map((comp) => {
                  const pct = Math.min(Math.round(comp.avg_score), 100);
                  return (
                    <div
                      key={comp.category}
                      className="p-3 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col gap-2"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-on-surface">{comp.category}</span>
                        <span className="font-label-numeric text-xs font-bold text-tertiary">{pct}%</span>
                      </div>
                      <div className="w-full bg-surface-container-highest h-1.5 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-secondary to-tertiary"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-outline font-label-numeric-sm">
                        {comp.challenges_count} question{comp.challenges_count !== 1 ? "s" : ""} evaluated
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
