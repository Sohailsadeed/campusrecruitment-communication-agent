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
import type { GuesstimateProgressResponse } from "../../api/analysis";

interface GuesstimateProgressDashboardProps {
  data?: GuesstimateProgressResponse;
  isLoading?: boolean;
}

export default function GuesstimateProgressDashboard({
  data,
  isLoading,
}: GuesstimateProgressDashboardProps) {
  const [activeTab, setActiveTab] = useState<"primary" | "four_rubrics">("four_rubrics");

  if (isLoading) {
    return (
      <Card>
        <div className="h-72 flex items-center justify-center text-outline text-xs gap-2">
          <span className="material-symbols-outlined animate-spin text-[20px]">sync</span>
          <span>Loading guesstimate &amp; market sizing progression...</span>
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
    latest_verdict: "No Drills",
  };
  const categories = data?.categories || [];
  const isSingleAttempt = summary.completed_drills === 1;

  const chartData = timeline.map((pt, idx) => ({
    index: idx + 1,
    name: `Attempt ${idx + 1} (${new Date(pt.created_at).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    })})`,
    shortName: `Att. ${idx + 1}`,
    score: pt.score,
    structure: pt.structure_score ?? null,
    proxy: pt.proxy_score ?? null,
    math: pt.math_score ?? null,
    sanity: pt.sanity_score ?? null,
    category: pt.category,
    difficulty: pt.difficulty,
    verdict: pt.verdict,
    benchmarkTarget: 85,
    benchmarkBaseline: 70,
  }));

  const latestPoint = timeline.length > 0 ? timeline[timeline.length - 1] : null;
  const latestRangeDiag = latestPoint?.range_diagnostic;
  const latestSensitivity = latestPoint?.sensitivity_analysis;
  const latestBranches = latestPoint?.candidate_branch_diagnostics || [];

  const getVerdictStyle = (v: string) => {
    if (v.includes("MBB") || v.includes("Tier-1")) return "text-tertiary bg-tertiary/15 border-tertiary/30";
    if (v.includes("Competitive")) return "text-emerald-400 bg-emerald-500/15 border-emerald-500/30";
    if (v.includes("Promising")) return "text-amber-400 bg-amber-400/15 border-amber-400/30";
    return "text-outline bg-surface-container border-outline-variant/30";
  };

  return (
    <Card padding="p-6">
      {/* Top Header Strip */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-outline-variant/30">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 rounded-lg bg-tertiary/10 text-tertiary flex items-center justify-center">
              <span className="material-symbols-outlined text-[18px]">query_stats</span>
            </div>
            <h3 className="text-lg font-bold text-on-surface">Guesstimate &amp; MECE Structuring Trajectory</h3>
            <span className="font-label-caps text-[10px] px-2 py-0.5 rounded-full bg-tertiary/20 text-tertiary font-bold">
              Consulting Sizing
            </span>
          </div>
          <p className="text-xs text-outline">
            Four-rubric progression tracking for MECE structuring, proxy assumptions, arithmetic flow, and reality checks.
          </p>
        </div>

        {/* Quick Stat Badges */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Avg Sizing Score</span>
            <span className="font-label-numeric text-sm font-bold text-on-surface">{summary.avg_score}%</span>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Peak Score</span>
            <span className="font-label-numeric text-sm font-bold text-tertiary">{summary.peak_score}%</span>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">MBB Verdict</span>
            <span className={`font-label-caps text-[10px] font-bold px-1.5 py-0.5 rounded mt-0.5 ${getVerdictStyle(summary.latest_verdict)}`}>
              {summary.latest_verdict}
            </span>
          </div>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="py-12 flex flex-col items-center justify-center text-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 text-tertiary flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">query_stats</span>
          </div>
          <p className="text-sm font-semibold text-on-surface">No Guesstimate Drills Recorded Yet</p>
          <p className="text-xs text-outline max-w-sm">
            Launch a Guesstimate Round drill to evaluate your MECE tree decomposition, math calculation speed, and Fermi assumption sanity.
          </p>
          <a
            href="/guesstimate"
            className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-tertiary text-on-tertiary font-semibold text-xs shadow-md hover:opacity-90 transition-opacity"
          >
            <span className="material-symbols-outlined text-[16px]">play_arrow</span>
            <span>Start Guesstimate Drill</span>
          </a>
        </div>
      ) : (
        <div className="mt-5 space-y-6">
          {/* Dual Trajectory View Switcher */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="inline-flex items-center p-1 rounded-xl bg-surface-container border border-outline-variant/30 gap-1">
              <button
                type="button"
                onClick={() => setActiveTab("four_rubrics")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "four_rubrics"
                    ? "bg-tertiary text-on-tertiary shadow-sm"
                    : "text-outline hover:text-on-surface"
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">stacked_line_chart</span>
                <span>Four-Rubric Trajectories</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("primary")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "primary"
                    ? "bg-tertiary text-on-tertiary shadow-sm"
                    : "text-outline hover:text-on-surface"
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">show_chart</span>
                <span>Primary Sizing Score</span>
              </button>
            </div>

            {/* Authoritative Weighting Policy Tag */}
            <div className="flex items-center gap-2 text-[11px] text-outline">
              <span className="material-symbols-outlined text-[15px] text-tertiary">scale</span>
              <span>Weights: <strong>35% MECE</strong> + <strong>25% Assumptions</strong> + <strong>20% Math</strong> + <strong>20% Sanity Check</strong></span>
            </div>
          </div>

          {/* Single-Attempt Baseline Callout */}
          {isSingleAttempt && (
            <div className="p-3.5 rounded-xl bg-surface-container-high/60 border border-outline-variant/30 flex items-center gap-3 text-xs text-on-surface-variant">
              <span className="material-symbols-outlined text-tertiary text-[20px] shrink-0">info</span>
              <div>
                <strong className="text-on-surface font-semibold">Baseline Established from Attempt 1: </strong>
                <span>Improvement over time is not yet measurable across multiple attempts. Complete further sizing drills to unlock longitudinal trajectory lines.</span>
              </div>
            </div>
          )}

          {/* Chart Display Area */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              {activeTab === "four_rubrics" ? (
                <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="shortName" stroke="#908fa0" fontSize={11} />
                  <YAxis stroke="#908fa0" fontSize={11} domain={[30, 100]} ticks={[40, 55, 70, 85, 100]} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const d = payload[0].payload;
                        return (
                          <div className="bg-surface-container-high border border-outline-variant/40 rounded-xl p-3 shadow-xl text-xs space-y-2 min-w-[210px]">
                            <div className="flex items-center justify-between gap-3">
                              <span className="font-bold text-on-surface">{d.name}</span>
                              <span className="text-[10px] text-outline uppercase">{d.category}</span>
                            </div>
                            <div className="text-tertiary font-label-numeric font-bold text-sm">
                              Overall Sizing: {d.score}%
                            </div>
                            <div className="space-y-1 pt-1.5 border-t border-outline-variant/20 text-[11px]">
                              <div className="flex items-center justify-between">
                                <span className="text-sky-400 flex items-center gap-1">
                                  <span className="w-2 h-2 rounded-full bg-sky-400 inline-block" />
                                  MECE Structuring (35%):
                                </span>
                                <strong className="text-on-surface">{d.structure != null ? `${d.structure}%` : "—"}</strong>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-emerald-400 flex items-center gap-1">
                                  <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
                                  Proxy Sanity (25%):
                                </span>
                                <strong className="text-on-surface">{d.proxy != null ? `${d.proxy}%` : "—"}</strong>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-orange-400 flex items-center gap-1">
                                  <span className="w-2 h-2 rounded-full bg-orange-400 inline-block" />
                                  Mental Math (20%):
                                </span>
                                <strong className="text-on-surface">{d.math != null ? `${d.math}%` : "—"}</strong>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-amber-400 flex items-center gap-1">
                                  <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
                                  Sanity Check (20%):
                                </span>
                                <strong className="text-on-surface">{d.sanity != null ? `${d.sanity}%` : "—"}</strong>
                              </div>
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine
                    y={85}
                    stroke="#4edea3"
                    strokeDasharray="4 4"
                    strokeOpacity={0.6}
                    label={{ value: "85% Target", position: "insideTopRight", fill: "#4edea3", fontSize: 10 }}
                  />
                  <ReferenceLine
                    y={70}
                    stroke="#f59e0b"
                    strokeDasharray="4 4"
                    strokeOpacity={0.4}
                    label={{ value: "70% Baseline", position: "insideBottomRight", fill: "#f59e0b", fontSize: 10 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="structure"
                    name="MECE Structure (35%)"
                    stroke="#38bdf8"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#38bdf8" }}
                    activeDot={{ r: 6 }}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="proxy"
                    name="Proxy Rigor (25%)"
                    stroke="#4ade80"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#4ade80" }}
                    activeDot={{ r: 6 }}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="math"
                    name="Mental Math (20%)"
                    stroke="#fb923c"
                    strokeWidth={2.2}
                    dot={{ r: 4, fill: "#fb923c" }}
                    activeDot={{ r: 6 }}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="sanity"
                    name="Sanity Check (20%)"
                    stroke="#facc15"
                    strokeWidth={2.2}
                    dot={{ r: 4, fill: "#facc15" }}
                    activeDot={{ r: 6 }}
                    connectNulls={false}
                  />
                </LineChart>
              ) : (
                <AreaChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="guessScoreGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4edea3" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#4edea3" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="shortName" stroke="#908fa0" fontSize={11} />
                  <YAxis stroke="#908fa0" fontSize={11} domain={[30, 100]} ticks={[40, 55, 70, 85, 100]} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const d = payload[0].payload;
                        return (
                          <div className="bg-surface-container-high border border-outline-variant/40 rounded-xl p-3 shadow-xl text-xs space-y-1.5">
                            <div className="flex items-center justify-between gap-3">
                              <span className="font-bold text-on-surface">{d.name}</span>
                              <span className="text-[10px] text-outline uppercase">{d.difficulty}</span>
                            </div>
                            <div className="text-tertiary font-label-numeric font-bold text-sm">
                              Score: {d.score}%
                            </div>
                            <span className={`inline-block font-label-caps text-[9px] px-1.5 py-0.5 rounded font-bold ${getVerdictStyle(d.verdict)}`}>
                              {d.verdict}
                            </span>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine
                    y={85}
                    stroke="#4edea3"
                    strokeDasharray="4 4"
                    strokeOpacity={0.8}
                    label={{ value: "MBB Tier-1 Target (85%)", position: "insideTopRight", fill: "#4edea3", fontSize: 10 }}
                  />
                  <ReferenceLine
                    y={70}
                    stroke="#f59e0b"
                    strokeDasharray="4 4"
                    strokeOpacity={0.5}
                    label={{ value: "Competitive Target (70%)", position: "insideBottomRight", fill: "#f59e0b", fontSize: 10 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke="#4edea3"
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#guessScoreGrad)"
                    dot={{ r: 4, fill: "#4edea3" }}
                  />
                </AreaChart>
              )}
            </ResponsiveContainer>
          </div>

          {/* Interactive Legend for 4 Rubrics */}
          {activeTab === "four_rubrics" && (
            <div className="flex flex-wrap items-center justify-center gap-5 text-xs text-on-surface-variant pt-1 border-t border-outline-variant/20">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-sky-400" />
                <span>MECE Structuring (35%)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                <span>Proxy &amp; Assumption Sanity (25%)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-orange-400" />
                <span>Mental Math Flow (20%)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                <span>Sanity Check &amp; Reality (20%)</span>
              </span>
            </div>
          )}

          {/* Compact Consulting Diagnostics Previews (Priorities 2, 3, 4 Preview) */}
          {latestPoint && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
              {/* Diagnostic 1: MECE Decomposition Preview */}
              <div className="p-4 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col justify-between gap-3">
                <div className="flex items-center justify-between">
                  <span className="font-label-caps text-[10px] uppercase text-outline font-bold flex items-center gap-1">
                    <span className="material-symbols-outlined text-sky-400 text-[15px]">account_tree</span>
                    Decomposition Rigor
                  </span>
                  <span className="font-label-numeric font-bold text-xs text-sky-400">
                    {latestPoint.structure_score != null ? `${latestPoint.structure_score}%` : "—"}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-on-surface font-semibold block mb-1">
                    Branch Evidence Audit
                  </span>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {latestBranches.length > 0 ? (
                      latestBranches.slice(0, 3).map((b, idx) => (
                        <span
                          key={idx}
                          className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                            b.status === "supported_mece"
                              ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                              : b.status === "confirmed_overlap"
                              ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                              : b.status === "omitted_segment"
                              ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                              : b.status === "unsupported_proxy"
                              ? "bg-yellow-500/15 text-yellow-300 border border-yellow-500/30"
                              : "bg-surface-container-high text-outline border border-outline-variant/30"
                          }`}
                        >
                          {b.branch_name}
                        </span>
                      ))
                    ) : (
                      <span className="text-[11px] text-outline italic">Consulting branches validated</span>
                    )}
                  </div>
                </div>
                <a
                  href={`/guesstimate/report/${latestPoint.session_id}`}
                  className="text-[11px] text-tertiary hover:underline font-semibold flex items-center gap-1"
                >
                  <span>Explore full tree in dossier</span>
                  <span className="material-symbols-outlined text-[13px]">arrow_forward</span>
                </a>
              </div>

              {/* Diagnostic 2: Estimate vs Plausible Range Preview */}
              <div className="p-4 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col justify-between gap-3">
                <div className="flex items-center justify-between">
                  <span className="font-label-caps text-[10px] uppercase text-outline font-bold flex items-center gap-1">
                    <span className="material-symbols-outlined text-tertiary text-[15px]">straighten</span>
                    Reality Check Gauge
                  </span>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${
                      latestRangeDiag?.status === "within_range"
                        ? "bg-tertiary/15 text-tertiary border border-tertiary/30"
                        : latestRangeDiag?.status === "below_range"
                        ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                        : latestRangeDiag?.status === "above_range"
                        ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                        : "bg-surface-container-high text-outline"
                    }`}
                  >
                    {latestRangeDiag?.summary_label || "Range Check"}
                  </span>
                </div>
                <div>
                  <div className="flex items-baseline justify-between text-xs mb-1">
                    <span className="text-outline">Estimate:</span>
                    <strong className="text-on-surface font-mono">
                      {typeof latestPoint.candidate_estimate === "object" && latestPoint.candidate_estimate
                        ? latestPoint.candidate_estimate.formatted_display || `${latestPoint.candidate_estimate.value} ${latestPoint.candidate_estimate.unit}`
                        : String(latestPoint.candidate_estimate || "Estimated")}
                    </strong>
                  </div>
                  <div className="flex items-baseline justify-between text-[11px] text-outline">
                    <span>Benchmark:</span>
                    <span className="font-mono">
                      {typeof latestPoint.plausible_range === "object" && latestPoint.plausible_range
                        ? latestPoint.plausible_range.formatted_display || `${latestPoint.plausible_range.min} - ${latestPoint.plausible_range.max}`
                        : String(latestPoint.plausible_range || "Plausible band")}
                    </span>
                  </div>
                </div>
                <span className="text-[10px] text-outline truncate" title={latestRangeDiag?.diagnostic_note}>
                  {latestRangeDiag?.diagnostic_note || "Reality benchmark validated against industry bounds."}
                </span>
              </div>

              {/* Diagnostic 3: Sensitivity Analysis Preview */}
              <div className="p-4 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col justify-between gap-3">
                <div className="flex items-center justify-between">
                  <span className="font-label-caps text-[10px] uppercase text-outline font-bold flex items-center gap-1">
                    <span className="material-symbols-outlined text-amber-400 text-[15px]">tune</span>
                    {latestSensitivity?.tornado_ranking && latestSensitivity.tornado_ranking.length > 1 ? "Tornado Sensitivity Ranking" : "Critical Sensitivity Driver"}
                  </span>
                  {latestSensitivity?.impact_percent != null && (
                    <span className="font-label-numeric font-bold text-xs text-amber-400">
                      ±{latestSensitivity.impact_percent}%
                    </span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-on-surface font-semibold block truncate">
                    {latestSensitivity?.driver_name || "Primary Assumption Driver"}
                  </span>
                  <p className="text-[11px] text-outline line-clamp-2 mt-0.5 leading-snug">
                    {latestSensitivity?.explanation || "Identifies which assumption creates the highest volatility in final sizing."}
                  </p>
                </div>
                <a
                  href={`/guesstimate/report/${latestPoint.session_id}`}
                  className="text-[11px] text-tertiary hover:underline font-semibold flex items-center gap-1"
                >
                  <span>Simulate swings in report</span>
                  <span className="material-symbols-outlined text-[13px]">arrow_forward</span>
                </a>
              </div>
            </div>
          )}

          {/* Category Breakdown Cards */}
          {categories.length > 0 && (
            <div className="pt-2">
              <span className="font-label-caps text-xs text-outline uppercase font-bold tracking-wider mb-3 block">
                Estimation Competencies by Problem Category
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {categories.map((cat, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl bg-surface-container border border-outline-variant/20 flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-on-surface">{cat.category}</span>
                      <span className="text-[10px] text-outline font-label-numeric font-medium">
                        {cat.drills_count} drill{cat.drills_count > 1 ? "s" : ""}
                      </span>
                    </div>
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-on-surface-variant">Avg Score:</span>
                      <span className="font-label-numeric text-base font-bold text-tertiary">
                        {cat.avg_score}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

