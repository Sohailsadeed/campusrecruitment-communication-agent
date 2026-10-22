import {
  AreaChart,
  Area,
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

  const chartData = timeline.map((pt, idx) => ({
    index: idx + 1,
    name: new Date(pt.created_at).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
    score: pt.score,
    structure: pt.structure_score,
    math: pt.math_score,
    proxy: pt.proxy_score,
    category: pt.category,
    difficulty: pt.difficulty,
    verdict: pt.verdict,
    benchmark: 85,
  }));

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
            Progression across market sizing, top-down tree decomposition, and Fermi problem estimations.
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
          {/* Main Progression Chart */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="guessScoreGrad" x1="0" y1="0" x2="0" y2="1">
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
                        <div className="bg-surface-container-high border border-outline-variant/40 rounded-xl p-3 shadow-xl text-xs space-y-1.5">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-bold text-on-surface">{d.category}</span>
                            <span className="text-[10px] text-outline uppercase">{d.difficulty}</span>
                          </div>
                          <div className="text-tertiary font-label-numeric font-bold text-sm">
                            Score: {d.score}%
                          </div>
                          <div className="grid grid-cols-3 gap-2 text-[10px] text-on-surface-variant pt-1 border-t border-outline-variant/20">
                            <span>Structure: {d.structure}%</span>
                            <span>Math: {d.math}%</span>
                            <span>Proxy: {d.proxy}%</span>
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
                  label={{
                    value: "MBB / Tier-1 Ready (85%)",
                    position: "insideTopRight",
                    fill: "#4edea3",
                    fontSize: 10,
                  }}
                />
                <ReferenceLine
                  y={70}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  strokeOpacity={0.5}
                  label={{
                    value: "Competitive (70%)",
                    position: "insideBottomRight",
                    fill: "#f59e0b",
                    fontSize: 10,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="score"
                  stroke="#4edea3"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#guessScoreGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

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
