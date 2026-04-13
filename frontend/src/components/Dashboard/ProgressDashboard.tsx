import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import Card from "../Common/Card";
import type { ProgressMetric } from "../../types";

interface ProgressDashboardProps {
  metrics: ProgressMetric[];
}

export default function ProgressDashboard({ metrics }: ProgressDashboardProps) {
  const data = metrics.map((m) => ({
    name: new Date(m.created_at).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
    clarity: m.clarity_score,
    pace: m.speaking_pace,
    eye: m.eye_contact_percentage,
  }));

  return (
    <Card>
      <h3 className="text-lg font-semibold mb-1">Progress over time</h3>
      <p className="text-xs text-slate-400 mb-4">
        Clarity, pace, and eye contact across sessions.
      </p>
      <div className="h-72">
        {data.length === 0 ? (
          <p className="text-sm text-slate-400 py-12 text-center">
            Record your first session to start tracking progress.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
              />
              <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1e1b2e",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="clarity"
                stroke="#a78bfa"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="pace"
                stroke="#6ee7b7"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="eye"
                stroke="#fbbf24"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
