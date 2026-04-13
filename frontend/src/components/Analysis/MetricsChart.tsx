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

  const clarityData = [
    {
      name: "Clarity",
      value: analysis.clarity_score,
      fill: "#a78bfa",
    },
  ];

  const fillerData = Object.entries(analysis.filler_words_list || {}).map(
    ([word, count]) => ({ word, count })
  );

  const presenceData = [
    { label: "Eye contact", value: analysis.eye_contact_percentage },
    { label: "Posture", value: analysis.posture_quality },
  ];

  return (
    <div className="grid md:grid-cols-2 gap-6">
      <Card>
        <h3 className="text-lg font-semibold mb-1">Clarity score</h3>
        <p className="text-xs text-slate-400 mb-4">
          Based on filler word density and delivery.
        </p>
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <RadialBarChart
              innerRadius="60%"
              outerRadius="100%"
              data={clarityData}
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
                background={{ fill: "rgba(255,255,255,0.06)" }}
                dataKey="value"
                cornerRadius={12}
              />
            </RadialBarChart>
          </ResponsiveContainer>
        </div>
        <div className="text-center -mt-40 relative z-10">
          <div className="text-4xl font-bold text-white">
            {Math.round(analysis.clarity_score)}
          </div>
          <div className="text-xs uppercase tracking-wider text-slate-400">
            / 100
          </div>
        </div>
      </Card>

      <Card>
        <h3 className="text-lg font-semibold mb-1">Speaking pace</h3>
        <p className="text-xs text-slate-400 mb-4">
          Words per minute (ideal 130-160).
        </p>
        <div className="flex items-center gap-6">
          <div className="text-5xl font-bold bg-gradient-to-br from-primary-300 to-primary-500 bg-clip-text text-transparent">
            {Math.round(analysis.speaking_pace)}
          </div>
          <div className="flex-1">
            <div className="h-3 rounded-full bg-white/10 relative overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary-500 to-primary-300 rounded-full"
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
                  background: "rgba(16,185,129,0.15)",
                  border: "1px dashed rgba(16,185,129,0.6)",
                }}
              />
            </div>
            <div className="text-xs text-slate-500 mt-2 flex justify-between">
              <span>0</span>
              <span>130</span>
              <span>160</span>
              <span>200+</span>
            </div>
          </div>
        </div>

        <div className="mt-8 space-y-3">
          {presenceData.map((p) => (
            <div key={p.label}>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-slate-300">{p.label}</span>
                <span className="text-slate-400">{Math.round(p.value)}%</span>
              </div>
              <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary-500 to-primary-300 rounded-full"
                  style={{ width: `${p.value}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="md:col-span-2">
        <h3 className="text-lg font-semibold mb-1">Filler word usage</h3>
        <p className="text-xs text-slate-400 mb-4">
          Total: {analysis.filler_words_count}
        </p>
        {fillerData.length > 0 ? (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={fillerData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="word" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: "rgba(139,92,246,0.1)" }}
                  contentStyle={{
                    backgroundColor: "#1e1b2e",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 12,
                  }}
                />
                <Bar dataKey="count" fill="#a78bfa" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-sm text-slate-400 py-8 text-center">
            No filler words detected. Excellent delivery!
          </p>
        )}
      </Card>
    </div>
  );
}
