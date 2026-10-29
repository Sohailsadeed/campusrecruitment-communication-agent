import {
  Bar,
  BarChart,
  CartesianGrid,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Card from "../Common/Card";
import type { SessionAnalysis } from "../../types";
import { AlertTriangle, Award, CheckCircle2, Repeat, MicOff, Clock } from "lucide-react";

interface MetricsChartProps {
  analysis: SessionAnalysis | null;
}

export default function MetricsChart({ analysis }: MetricsChartProps) {
  if (!analysis) {
    return (
      <Card>
        <p className="text-slate-400 text-sm">No analysis available yet.</p>
      </Card>
    );
  }

  // Extract JAM metadata
  const jam = analysis.filler_words_list?._jam || {};
  const rawFillers: Record<string, number> = {};
  for (const [k, v] of Object.entries(analysis.filler_words_list || {})) {
    if (k !== "_jam" && typeof v === "number" && v > 0) {
      rawFillers[k] = v;
    }
  }

  const jamScore = Math.round(jam.jam_score ?? analysis.clarity_score ?? 70);
  const jamVerdict = jam.jam_verdict || (jamScore >= 75 ? "Qualified ✅" : "Challenged ⚠️");
  const infractions: string[] = jam.jam_infractions || [];
  const repeatedWords: Record<string, number> = jam.repeated_words || {};

  const fillerData = Object.entries(rawFillers).map(([word, count]) => ({
    word,
    count,
  }));

  const isMaster = jamScore >= 85;
  const isQualified = jamScore >= 70;

  const radialData = [
    {
      name: "JAM Score",
      value: jamScore,
      fill: isMaster ? "#10b981" : isQualified ? "#6366f1" : "#f59e0b",
    },
  ];

  const presenceData = [
    { label: "Eye contact", value: analysis.eye_contact_percentage },
    { label: "Posture quality", value: analysis.posture_quality },
  ];

  return (
    <div className="space-y-6">
      {/* JAM Official Verdict Banner */}
      <div className="p-6 sm:p-8 rounded-2xl bg-gradient-to-br from-violet-600 via-violet-500 to-fuchsia-500 shadow-lg text-white relative overflow-hidden flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="absolute -top-12 -right-12 w-48 h-48 bg-white/10 rounded-full blur-2xl" aria-hidden />
        <div className="space-y-2 relative z-10">
          <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1 rounded-full bg-white/20 border border-white/25 text-white backdrop-blur-xs">
            <Award className="w-3.5 h-3.5 text-amber-300" />
            Official JAM Adjudication Report
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight flex items-center gap-2.5 text-white">
            {jamVerdict}
          </h2>
          <p className="text-sm text-violet-100 max-w-xl">
            Evaluated against the 3 Cardinal JAM Rules: No Hesitation, No Repetition, and No Deviation.
          </p>

          {/* Infraction tags */}
          {infractions.length > 0 ? (
            <div className="flex flex-wrap gap-2 pt-2">
              {infractions.map((inf, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-white/20 border border-white/30 text-white font-medium"
                >
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-300" />
                  {inf}
                </span>
              ))}
            </div>
          ) : (
            <div className="inline-flex items-center gap-1.5 text-xs text-emerald-200 font-medium pt-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-300" />
              Clean round with zero major rule infractions!
            </div>
          )}
        </div>

        {/* Big Score Box */}
        <div className="flex items-center gap-4 bg-white/15 border border-white/25 p-5 rounded-2xl min-w-[160px] justify-center relative z-10 backdrop-blur-xs">
          <div className="text-center">
            <div className="text-4xl font-black text-white">
              {jamScore}
            </div>
            <div className="text-[11px] uppercase tracking-widest text-violet-200 font-bold mt-0.5">
              JAM Score / 100
            </div>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* JAM Score Gauge */}
        <Card>
          <h3 className="text-lg font-bold text-slate-900 mb-1 flex items-center gap-2">
            <Award className="w-4 h-4 text-violet-600" /> Fluency &amp; Adherence
          </h3>
          <p className="text-xs text-slate-500 mb-4">
            Penalizes hesitation sounds, repetition loops, and pacing extremes.
          </p>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius="65%"
                outerRadius="100%"
                data={radialData}
                startAngle={90}
                endAngle={-270}
              >
                <PolarAngleAxis
                  type="number"
                  domain={[0, 100]}
                  angleAxisId={0}
                  tick={false}
                />
                <RadialBar
                  background={{ fill: "rgba(0,0,0,0.04)" }}
                  dataKey="value"
                  cornerRadius={12}
                />
              </RadialBarChart>
            </ResponsiveContainer>
          </div>
          <div className="text-center -mt-40 relative z-10">
            <div className="text-4xl font-extrabold text-slate-900">
              {jamScore}
            </div>
            <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              / 100
            </div>
          </div>
        </Card>

        {/* Speaking Pace & Presence */}
        <Card>
          <h3 className="text-lg font-bold text-slate-900 mb-1 flex items-center gap-2">
            <Clock className="w-4 h-4 text-emerald-600" /> JAM Speaking Pace
          </h3>
          <p className="text-xs text-slate-500 mb-4">
            Ideal range is 130–160 WPM for sustained 60-second delivery.
          </p>
          <div className="flex items-center gap-6">
            <div className="text-5xl font-extrabold text-violet-600">
              {Math.round(analysis.speaking_pace)}
            </div>
            <div className="flex-1">
              <div className="h-3 rounded-full bg-slate-100 border border-slate-200 relative overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 bg-violet-600 rounded-full"
                  style={{
                    width: `${Math.min(
                      100,
                      (analysis.speaking_pace / 200) * 100
                    )}%`,
                  }}
                />
                <div
                  className="absolute inset-y-0"
                  style={{
                    left: "65%",
                    right: "20%",
                    background: "rgba(16,185,129,0.2)",
                    border: "1px dashed rgba(16,185,129,0.8)",
                  }}
                />
              </div>
              <div className="text-xs text-slate-500 mt-2 flex justify-between font-medium">
                <span>0</span>
                <span className="text-emerald-600 font-semibold">130</span>
                <span className="text-emerald-600 font-semibold">160</span>
                <span>200+</span>
              </div>
            </div>
          </div>

          <div className="mt-8 space-y-3">
            {presenceData.map((p) => (
              <div key={p.label}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-700 font-medium">{p.label}</span>
                  <span className="text-slate-500 font-semibold">{Math.round(p.value)}%</span>
                </div>
                <div className="h-2 rounded-full bg-slate-100 border border-slate-200 overflow-hidden">
                  <div
                    className="h-full bg-violet-600 rounded-full"
                    style={{ width: `${p.value}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Cardinal Rule 1: Hesitation (Filler Words Breakdown) */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <MicOff className="w-4 h-4 text-rose-500" /> Cardinal Rule 1: Hesitation
            </h3>
            <p className="text-xs text-slate-500">
              Total hesitation sounds detected: <strong>{analysis.filler_words_count}</strong>
            </p>
          </div>
          {analysis.filler_words_count === 0 ? (
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
              Zero Hesitation 🌟
            </span>
          ) : (
            <span className="text-xs font-semibold text-rose-700 bg-rose-50 px-3 py-1 rounded-full border border-rose-200">
              {analysis.filler_words_count} Hesitations
            </span>
          )}
        </div>

        {fillerData.length > 0 ? (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={fillerData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="word" stroke="#64748b" fontSize={12} />
                <YAxis stroke="#64748b" fontSize={12} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: "rgba(124,58,237,0.06)" }}
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    border: "1px solid #e2e8f0",
                    borderRadius: 12,
                    boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                  }}
                />
                <Bar dataKey="count" fill="#7c3aed" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-sm text-emerald-800 py-6 text-center bg-emerald-50/60 rounded-xl border border-emerald-200 font-medium">
            No hesitation or filler sounds detected during the entire 60 seconds!
          </p>
        )}
      </Card>

      {/* Acoustic Pauses & Hesitations Card */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Clock className="w-4 h-4 text-violet-600" /> Acoustic Pauses &amp; Silence Analysis
            </h3>
            <p className="text-xs text-slate-500">
              Separates micro-hesitations (0.5s&ndash;1.19s) from real pauses (&ge; 1.2s) using millisecond word alignment.
            </p>
          </div>
          <span
            className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
              (jam.total_pause_time ?? 0) <= 3.5
                ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                : (jam.total_pause_time ?? 0) <= 6.0
                ? "text-amber-700 bg-amber-50 border-amber-200"
                : "text-rose-700 bg-rose-50 border-rose-200"
            }`}
          >
            {(jam.total_pause_time ?? 0) <= 3.5
              ? "Continuous Flow 🌊"
              : (jam.total_pause_time ?? 0) <= 6.0
              ? "Moderate Pauses ⏸️"
              : "Hesitant Stoppages ⚠️"}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center">
            <div className="text-2xl font-bold text-violet-600">
              {Number(jam.total_pause_time ?? 0).toFixed(1)}s
            </div>
            <div className="text-[11px] text-slate-500 font-medium mt-1">
              Real Pause Time
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center">
            <div className="text-2xl font-bold text-slate-900">
              {Number(jam.pause_count ?? 0)}
            </div>
            <div className="text-[11px] text-slate-500 font-medium mt-1">
              Pauses (&ge; 1.2s)
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center">
            <div className="text-2xl font-bold text-amber-600">
              {Number(jam.longest_pause ?? 0).toFixed(1)}s
            </div>
            <div className="text-[11px] text-slate-500 font-medium mt-1">
              Longest Single Freeze
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center">
            <div className="text-2xl font-bold text-sky-600">
              {Number(jam.micro_hesitation_count ?? 0)}
            </div>
            <div className="text-[11px] text-slate-500 font-medium mt-1">
              Micro-hesitations
            </div>
          </div>
        </div>
      </Card>

      {/* Cardinal Rule 2: Repetition */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Repeat className="w-4 h-4 text-amber-600" /> Cardinal Rule 2: Repetition
            </h3>
            <p className="text-xs text-slate-500">
              Words repeated 3 or more times (excluding common grammar words).
            </p>
          </div>
          {Object.keys(repeatedWords).length === 0 ? (
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
              No Repetitions 🌟
            </span>
          ) : (
            <span className="text-xs font-semibold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
              {Object.keys(repeatedWords).length} Repetitions Found
            </span>
          )}
        </div>

        {Object.keys(repeatedWords).length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-2">
            {Object.entries(repeatedWords).map(([word, count]) => (
              <span
                key={word}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs font-medium"
              >
                <span>&quot;{word}&quot;</span>
                <span className="px-1.5 py-0.5 rounded-md bg-amber-200/70 text-amber-800 font-bold">
                  {count}x
                </span>
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm text-emerald-800 py-4 text-center bg-emerald-50/60 rounded-xl border border-emerald-200 font-medium">
            Excellent vocabulary breadth! You advanced your ideas without looping on the same words.
          </p>
        )}
      </Card>
    </div>
  );
}
