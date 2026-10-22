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
import type { HRProgressResponse } from "../../api/analysis";

interface HRProgressDashboardProps {
  data?: HRProgressResponse;
  isLoading?: boolean;
}

export default function HRProgressDashboard({
  data,
  isLoading,
}: HRProgressDashboardProps) {
  if (isLoading) {
    return (
      <Card>
        <div className="h-72 flex items-center justify-center text-outline text-xs gap-2">
          <span className="material-symbols-outlined animate-spin text-[20px]">sync</span>
          <span>Loading HR &amp; behavioral interview progression...</span>
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
    ownership: pt.avg_ownership_score,
    star: pt.avg_star_completeness,
    specificity: pt.avg_specificity_score,
    role: pt.role,
    target_company: pt.target_company,
    verdict: pt.verdict,
    benchmark: 85,
  }));

  const getVerdictStyle = (v: string) => {
    if (v.includes("Executive") || v.includes("Ready")) return "text-primary bg-primary/15 border-primary/30";
    if (v.includes("Strong")) return "text-emerald-400 bg-emerald-500/15 border-emerald-500/30";
    if (v.includes("Developing")) return "text-amber-400 bg-amber-400/15 border-amber-400/30";
    return "text-outline bg-surface-container border-outline-variant/30";
  };

  return (
    <Card padding="p-6">
      {/* Top Header Strip */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-outline-variant/30">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <span className="material-symbols-outlined text-[18px]">diversity_3</span>
            </div>
            <h3 className="text-lg font-bold text-on-surface">HR &amp; Behavioral STAR Method Trajectory</h3>
            <span className="font-label-caps text-[10px] px-2 py-0.5 rounded-full bg-primary/20 text-primary font-bold">
              STAR Coach
            </span>
          </div>
          <p className="text-xs text-outline">
            Chronological progression across Situation-Task-Action-Result narratives and personal agency (&quot;I&quot; ownership).
          </p>
        </div>

        {/* Quick Stat Badges */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Avg Behavioral Score</span>
            <span className="font-label-numeric text-sm font-bold text-on-surface">{summary.avg_score}%</span>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col">
            <span className="font-label-caps text-[9px] uppercase text-outline font-bold">Peak Score</span>
            <span className="font-label-numeric text-sm font-bold text-primary">{summary.peak_score}%</span>
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
          <div className="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 text-primary flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">diversity_3</span>
          </div>
          <p className="text-sm font-semibold text-on-surface">No HR Behavioral Drills Recorded Yet</p>
          <p className="text-xs text-outline max-w-sm">
            Launch an HR mock interview to analyze your STAR framework completeness, personal ownership (&quot;I&quot; vs &quot;we&quot; agency), and quantified executive storytelling.
          </p>
          <a
            href="/hr"
            className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-on-primary font-semibold text-xs shadow-md hover:opacity-90 transition-opacity"
          >
            <span className="material-symbols-outlined text-[16px]">play_arrow</span>
            <span>Start HR Behavioral Drill</span>
          </a>
        </div>
      ) : (
        <div className="mt-5 space-y-6">
          {/* Main Progression Chart */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="hrScoreGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#c0c1ff" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#c0c1ff" stopOpacity={0.0} />
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
                            <span className="font-bold text-on-surface">{d.role}</span>
                            {d.target_company && (
                              <span className="text-[10px] text-primary font-bold">{d.target_company}</span>
                            )}
                          </div>
                          <div className="text-primary font-label-numeric font-bold text-sm">
                            Overall Score: {d.score}%
                          </div>
                          <div className="grid grid-cols-3 gap-2 text-[10px] text-on-surface-variant pt-1 border-t border-outline-variant/20">
                            <span>STAR: {d.star}%</span>
                            <span>Agency: {d.ownership}%</span>
                            <span>Data: {d.specificity}%</span>
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
                  stroke="#c0c1ff"
                  strokeDasharray="4 4"
                  strokeOpacity={0.8}
                  label={{
                    value: "Executive Ready (85%)",
                    position: "insideTopRight",
                    fill: "#c0c1ff",
                    fontSize: 10,
                  }}
                />
                <ReferenceLine
                  y={70}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  strokeOpacity={0.5}
                  label={{
                    value: "Strong STAR (70%)",
                    position: "insideBottomRight",
                    fill: "#f59e0b",
                    fontSize: 10,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="score"
                  stroke="#c0c1ff"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#hrScoreGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Behavioral Competencies Breakdown Cards */}
          {competencies.length > 0 && (
            <div className="pt-2">
              <span className="font-label-caps text-xs text-outline uppercase font-bold tracking-wider mb-3 block">
                Behavioral Competency Pillars
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                {competencies.map((comp, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl bg-surface-container border border-outline-variant/20 flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-on-surface line-clamp-1">{comp.track}</span>
                      <span className="text-[10px] text-outline font-label-numeric font-medium">
                        {comp.drills_count}
                      </span>
                    </div>
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-on-surface-variant">Avg:</span>
                      <span className="font-label-numeric text-base font-bold text-primary">
                        {comp.avg_score}%
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
