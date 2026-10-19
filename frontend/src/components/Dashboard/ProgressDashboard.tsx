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
      <h3 className="text-lg font-bold text-on-surface mb-1">Progress Over Time</h3>
      <p className="text-xs text-outline mb-4">
        Fluency, pace, and presence stability across recorded takes.
      </p>
      <div className="h-72">
        {data.length === 0 ? (
          <p className="text-sm text-outline py-12 text-center">
            Record your first session to start tracking progress.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
              />
              <XAxis dataKey="name" stroke="#908fa0" fontSize={11} />
              <YAxis stroke="#908fa0" fontSize={11} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1d1f27",
                  border: "1px solid #464554",
                  borderRadius: 10,
                  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                  color: "#e1e2ec",
                  fontSize: "12px",
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#c7c4d7" }} />
              <Line
                type="monotone"
                dataKey="clarity"
                name="JAM Fluency Score"
                stroke="#c0c1ff"
                strokeWidth={2.5}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="pace"
                name="Speaking Pace (WPM)"
                stroke="#4edea3"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="eye"
                name="Presence (%)"
                stroke="#7bd0ff"
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

