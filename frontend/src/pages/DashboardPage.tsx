import { useState } from "react";
import StatisticsCards from "../components/Dashboard/StatisticsCards";
import ProgressDashboard from "../components/Dashboard/ProgressDashboard";
import TechnicalProgressDashboard from "../components/Dashboard/TechnicalProgressDashboard";
import SessionHistory from "../components/Dashboard/SessionHistory";
import Loading from "../components/Common/Loading";
import {
  useProgressMetrics,
  useProgressSummary,
  useSessions,
  useTechnicalProgress,
} from "../hooks/useSessions";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<"all" | "technical" | "jam">("all");
  const summaryQuery = useProgressSummary();
  const metricsQuery = useProgressMetrics();
  const sessionsQuery = useSessions();
  const techQuery = useTechnicalProgress();

  if (summaryQuery.isLoading || sessionsQuery.isLoading || metricsQuery.isLoading) {
    return <Loading label="Loading dashboard" />;
  }

  const summary = summaryQuery.data;
  const metrics = metricsQuery.data || [];
  const sessions = sessionsQuery.data || [];
  const techData = techQuery.data;

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

      {/* Analytics Track Filter Tabs */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-surface-container border border-outline-variant/30">
          <button
            type="button"
            onClick={() => setActiveTab("all")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "all"
                ? "bg-surface-container-high text-on-surface shadow-sm font-bold"
                : "text-outline hover:text-on-surface"
            }`}
          >
            All Tracks
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("technical")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              activeTab === "technical"
                ? "bg-secondary/20 text-secondary border border-secondary/30 shadow-sm font-bold"
                : "text-outline hover:text-on-surface"
            }`}
          >
            <span className="material-symbols-outlined text-[15px]">terminal</span>
            <span>Technical Drill Trajectory</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("jam")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              activeTab === "jam"
                ? "bg-primary/20 text-primary border border-primary/30 shadow-sm font-bold"
                : "text-outline hover:text-on-surface"
            }`}
          >
            <span className="material-symbols-outlined text-[15px]">sensors</span>
            <span>JAM Fluency Telemetry</span>
          </button>
        </div>

        <span className="text-xs text-outline font-label-numeric-sm hidden sm:inline">
          {activeTab === "technical"
            ? `${techData?.summary.completed_drills || 0} Technical Drills Evaluated`
            : activeTab === "jam"
            ? `${metrics.length} JAM Sessions Evaluated`
            : `${(techData?.summary.completed_drills || 0) + metrics.length} Total Evaluated Rounds`}
        </span>
      </div>

      {/* Technical Interview Trajectory Visual Chart */}
      {(activeTab === "all" || activeTab === "technical") && (
        <TechnicalProgressDashboard data={techData} isLoading={techQuery.isLoading} />
      )}

      {/* JAM Speech Delivery & Fluency Visual Chart */}
      {(activeTab === "all" || activeTab === "jam") && (
        <ProgressDashboard metrics={metrics} />
      )}

      {/* Filtered Recent Sessions History */}
      <SessionHistory
        sessions={
          activeTab === "technical"
            ? sessions.filter((s) => s.round_type === "technical")
            : activeTab === "jam"
            ? sessions.filter((s) => s.round_type !== "technical")
            : sessions
        }
      />
    </div>
  );
}
