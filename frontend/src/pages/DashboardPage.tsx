import StatisticsCards from "../components/Dashboard/StatisticsCards";
import ProgressDashboard from "../components/Dashboard/ProgressDashboard";
import SessionHistory from "../components/Dashboard/SessionHistory";
import Loading from "../components/Common/Loading";
import {
  useProgressMetrics,
  useProgressSummary,
  useSessions,
} from "../hooks/useSessions";

export default function DashboardPage() {
  const summaryQuery = useProgressSummary();
  const metricsQuery = useProgressMetrics();
  const sessionsQuery = useSessions();

  if (summaryQuery.isLoading || sessionsQuery.isLoading || metricsQuery.isLoading) {
    return <Loading label="Loading dashboard" />;
  }

  const summary = summaryQuery.data;
  const metrics = metricsQuery.data || [];
  const sessions = sessionsQuery.data || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-slate-400">Your practice trends at a glance.</p>
      </div>

      {summary ? <StatisticsCards summary={summary} /> : null}
      <ProgressDashboard metrics={metrics} />
      <SessionHistory sessions={sessions} />
    </div>
  );
}
