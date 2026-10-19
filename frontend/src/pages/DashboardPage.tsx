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
      {/* VerbalIQ Performance Hub Banner */}
      <div className="relative overflow-hidden rounded-xl bg-surface-container-low border border-outline-variant/30 px-6 sm:px-8 py-6 sm:py-8 shadow-xl text-on-surface">
        <div className="absolute -top-12 -right-12 w-48 h-48 bg-primary/10 rounded-full blur-2xl" aria-hidden />
        <div className="absolute -bottom-16 -left-10 w-56 h-56 bg-secondary/10 rounded-full blur-3xl" aria-hidden />
        <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-highest text-tertiary font-label-numeric-sm text-[11px] font-medium mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse" />
              Pattern &amp; Progress Analytics
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-on-surface mt-1">Telemetry Dashboard</h1>
            <p className="text-on-surface-variant text-sm mt-1">Cross-session tracking of speaking pace, hesitation indices, and STAR delivery.</p>
          </div>
          <a
            href="/record"
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-primary text-on-primary hover:bg-primary-fixed-dim font-semibold shadow-md self-start sm:self-auto text-xs transition-all"
          >
            <span className="material-symbols-outlined text-[18px]">play_arrow</span>
            <span>+ Quick Launch Drill</span>
          </a>
        </div>
      </div>

      {summary ? <StatisticsCards summary={summary} /> : null}
      <ProgressDashboard metrics={metrics} />
      <SessionHistory sessions={sessions} />
    </div>
  );
}
