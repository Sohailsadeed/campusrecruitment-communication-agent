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
import type { TechnicalProgressResponse } from "../../api/analysis";

interface TechnicalProgressDashboardProps {
  data?: TechnicalProgressResponse;
  isLoading?: boolean;
}

export default function TechnicalProgressDashboard({
  data,
  isLoading,
}: TechnicalProgressDashboardProps) {
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-outline-variant/30">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 rounded-lg bg-secondary/10 text-secondary flex items-center justify-center">
              <span className="material-symbols-outlined text-[18px]">terminal</span>
            </div>
            <h3 className="text-lg font-bold text-on-surface">Technical Interview Trajectory</h3>
            <span className="font-label-caps text-[10px] px-2 py-0.5 rounded-full bg-secondary-container/20 text-secondary font-bold">
              LangGraph & Nemotron
            </span>
          </div>
          <p className="text-xs text-outline">
            Chronological progression across architecture, system design, and engineering interviews.
          </p>
        </div>

        {/* Quick Stat Badges */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Avg Technical Score</span>
            <span className="font-label-numeric text-sm font-bold text-on-surface">{summary.avg_score}%</span>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Peak Score</span>
            <span className="font-label-numeric text-sm font-bold text-tertiary">{summary.peak_score}%</span>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Readiness Verdict</span>
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
            Launch a Technical Round mock interview to start tracking your architectural reasoning, system trade-offs, and hire-readiness over time.
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
          {/* Main Chart */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
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
                        <div className="p-3.5 rounded-xl bg-[#1d1f27] border border-[#464554] shadow-2xl text-xs flex flex-col gap-1.5 min-w-[200px]">
                          <div className="flex items-center justify-between border-b border-outline-variant/30 pb-1.5 mb-0.5">
                            <span className="font-bold text-on-surface">{d.role}</span>
                            <span className="font-label-numeric-sm text-[10px] text-outline">{d.name}</span>
                          </div>
                          {d.target_company && (
                            <span className="text-[11px] text-outline">Target: {d.target_company}</span>
                          )}
                          <div className="flex items-center justify-between pt-1">
                            <span className="text-outline">Score:</span>
                            <span className="font-label-numeric font-bold text-sm text-tertiary">{d.score} / 100</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-outline">Adjudication:</span>
                            <span className={`font-semibold px-2 py-0.5 rounded text-[10px] ${getVerdictStyle(d.verdict)}`}>
                              {d.verdict}
                            </span>
                          </div>
                          <div className="text-[10px] text-outline pt-1 border-t border-outline-variant/20 mt-1">
                            {d.questions_count} questions synthesized & evaluated
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />

                {/* Benchmark Lines */}
                <ReferenceLine
                  y={85}
                  stroke="#c0c1ff"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  label={{
                    value: "Staff Strong Hire (85+)",
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
                    value: "Competitive Benchmark (70+)",
                    position: "insideBottomRight",
                    fill: "#f59e0b",
                    fontSize: 9,
                  }}
                />

                <Area
                  type="monotone"
                  dataKey="score"
                  name="Technical Readiness Score"
                  stroke="#4edea3"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#techScoreGrad)"
                  dot={{ r: 4, fill: "#4edea3", stroke: "#121318", strokeWidth: 2 }}
                  activeDot={{ r: 6, fill: "#4edea3", stroke: "#ffffff", strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
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
