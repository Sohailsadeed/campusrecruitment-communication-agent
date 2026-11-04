import { useState } from "react";
import StatisticsCards from "../components/Dashboard/StatisticsCards";
import PlacementReadinessMatrix from "../components/Dashboard/PlacementReadinessMatrix";
import CurriculumCoachCard from "../components/Dashboard/CurriculumCoachCard";
import ProgressDashboard from "../components/Dashboard/ProgressDashboard";
import TechnicalProgressDashboard from "../components/Dashboard/TechnicalProgressDashboard";
import GuesstimateProgressDashboard from "../components/Dashboard/GuesstimateProgressDashboard";
import HRProgressDashboard from "../components/Dashboard/HRProgressDashboard";
import SessionHistory from "../components/Dashboard/SessionHistory";
import Loading from "../components/Common/Loading";
import {
  useProgressMetrics,
  useProgressSummary,
  useSessions,
  useTechnicalProgress,
  useGuesstimateProgress,
  useHRProgress,
  usePlacementReadiness,
} from "../hooks/useSessions";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<"all" | "jam" | "technical" | "guesstimate" | "hr">("all");
  const summaryQuery = useProgressSummary();
  const metricsQuery = useProgressMetrics();
  const sessionsQuery = useSessions();
  const techQuery = useTechnicalProgress();
  const guesstimateQuery = useGuesstimateProgress();
  const hrQuery = useHRProgress();
  const readinessQuery = usePlacementReadiness();

  if (summaryQuery.isLoading || sessionsQuery.isLoading || metricsQuery.isLoading) {
    return <Loading label="Loading placement intelligence dashboard" />;
  }

  const summary = summaryQuery.data;
  const metrics = metricsQuery.data || [];
  const sessions = sessionsQuery.data || [];
  const techData = techQuery.data;
  const guesstimateData = guesstimateQuery.data;
  const hrData = hrQuery.data;
  const readinessData = readinessQuery.data;

  // Filter sessions by selected round
  const filteredSessions = sessions.filter((s) => {
    if (activeTab === "all") return true;
    if (activeTab === "technical") return s.round_type === "technical";
    if (activeTab === "guesstimate") return s.round_type === "guesstimate";
    if (activeTab === "hr") return s.round_type === "hr";
    if (activeTab === "jam") return !s.round_type || s.round_type === "jam" || s.round_type === "general";
    return true;
  });

  return (
    <div className="space-y-8">
      {/* VerbalIQ Performance Hub Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-surface-container-low border border-outline-variant/30 px-6 sm:px-8 py-6 sm:py-8 shadow-xl text-on-surface">
        <div className="absolute -top-12 -right-12 w-48 h-48 bg-primary/10 rounded-full blur-2xl" aria-hidden />
        <div className="absolute -bottom-16 -left-10 w-56 h-56 bg-secondary/10 rounded-full blur-3xl" aria-hidden />
        <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-highest text-tertiary font-label-numeric-sm text-[11px] font-medium mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse" />
              Unified 4-Round Placement Intelligence
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-on-surface mt-1">
              Placement Preparation Telemetry Hub
            </h1>
            <p className="text-on-surface-variant text-sm mt-1 max-w-2xl">
              Cross-round diagnostic tracking across JAM delivery fluency, technical architecture, consulting guesstimates, and STAR leadership ownership.
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
            <a
              href="/record"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/30 text-on-surface font-semibold text-xs transition-colors"
            >
              <span className="material-symbols-outlined text-[16px] text-primary">sensors</span>
              <span>JAM</span>
            </a>
            <a
              href="/technical"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/30 text-on-surface font-semibold text-xs transition-colors"
            >
              <span className="material-symbols-outlined text-[16px] text-secondary">terminal</span>
              <span>Technical</span>
            </a>
            <a
              href="/guesstimate"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/30 text-on-surface font-semibold text-xs transition-colors"
            >
              <span className="material-symbols-outlined text-[16px] text-tertiary">query_stats</span>
              <span>Guesstimate</span>
            </a>
            <a
              href="/hr"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary text-on-primary hover:opacity-90 font-semibold text-xs shadow-md transition-all"
            >
              <span className="material-symbols-outlined text-[16px]">diversity_3</span>
              <span>HR Drill</span>
            </a>
          </div>
        </div>
      </div>

      {/* LAYER 1: 4-Round Placement Readiness Matrix */}
      <PlacementReadinessMatrix
        data={readinessData}
        isLoading={readinessQuery.isLoading}
      />

      {/* Autonomous Curriculum Coach Agent */}
      <CurriculumCoachCard />

      {/* High-Level Practice Stats Strip */}
      {summary ? <StatisticsCards summary={summary} /> : null}

      {/* LAYER 2: Round-Specific Visual Diagnostics & Filter Tabs */}
      <div className="space-y-5">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-surface-container border border-outline-variant/30 overflow-x-auto">
            <button
              type="button"
              onClick={() => setActiveTab("all")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "all"
                  ? "bg-surface-container-high text-on-surface shadow-sm font-bold"
                  : "text-outline hover:text-on-surface"
              }`}
            >
              All Trajectories
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("jam")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "jam"
                  ? "bg-primary/20 text-primary border border-primary/30 shadow-sm font-bold"
                  : "text-outline hover:text-on-surface"
              }`}
            >
              <span className="material-symbols-outlined text-[15px]">sensors</span>
              <span>Round 01: JAM Fluency</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("technical")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "technical"
                  ? "bg-secondary/20 text-secondary border border-secondary/30 shadow-sm font-bold"
                  : "text-outline hover:text-on-surface"
              }`}
            >
              <span className="material-symbols-outlined text-[15px]">terminal</span>
              <span>Round 02: Technical</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("guesstimate")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "guesstimate"
                  ? "bg-tertiary/20 text-tertiary border border-tertiary/30 shadow-sm font-bold"
                  : "text-outline hover:text-on-surface"
              }`}
            >
              <span className="material-symbols-outlined text-[15px]">query_stats</span>
              <span>Round 03: Guesstimate</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("hr")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "hr"
                  ? "bg-primary/20 text-primary border border-primary/30 shadow-sm font-bold"
                  : "text-outline hover:text-on-surface"
              }`}
            >
              <span className="material-symbols-outlined text-[15px]">diversity_3</span>
              <span>Round 04: HR &amp; Behavioral</span>
            </button>
          </div>

          <span className="text-xs text-outline font-label-numeric-sm hidden sm:inline">
            Showing {filteredSessions.length} sessions in current view
          </span>
        </div>

        {/* Round 01: JAM Delivery & Fluency Chart */}
        {(activeTab === "all" || activeTab === "jam") && (
          <div className="space-y-2">
            {activeTab === "all" && (
              <div className="flex items-center gap-2 pt-2">
                <span className="font-label-caps text-xs text-outline uppercase font-bold">
                  Round 01 &middot; JAM Fluency &amp; Delivery Dynamics
                </span>
              </div>
            )}
            <ProgressDashboard metrics={metrics} />
          </div>
        )}

        {/* Round 02: Technical Interview Trajectory Chart */}
        {(activeTab === "all" || activeTab === "technical") && (
          <div className="space-y-2">
            {activeTab === "all" && (
              <div className="flex items-center gap-2 pt-2">
                <span className="font-label-caps text-xs text-outline uppercase font-bold">
                  Round 02 &middot; Technical Architecture &amp; Logic Trajectory
                </span>
              </div>
            )}
            <TechnicalProgressDashboard
              data={techData}
              isLoading={techQuery.isLoading}
            />
          </div>
        )}

        {/* Round 03: Guesstimate & Market Sizing Chart */}
        {(activeTab === "all" || activeTab === "guesstimate") && (
          <div className="space-y-2">
            {activeTab === "all" && (
              <div className="flex items-center gap-2 pt-2">
                <span className="font-label-caps text-xs text-outline uppercase font-bold">
                  Round 03 &middot; Guesstimate &amp; MECE Tree Decomposition Trajectory
                </span>
              </div>
            )}
            <GuesstimateProgressDashboard
              data={guesstimateData}
              isLoading={guesstimateQuery.isLoading}
            />
          </div>
        )}

        {/* Round 04: HR & Behavioral STAR Method Chart */}
        {(activeTab === "all" || activeTab === "hr") && (
          <div className="space-y-2">
            {activeTab === "all" && (
              <div className="flex items-center gap-2 pt-2">
                <span className="font-label-caps text-xs text-outline uppercase font-bold">
                  Round 04 &middot; HR STAR Method &amp; Personal Ownership Trajectory
                </span>
              </div>
            )}
            <HRProgressDashboard
              data={hrData}
              isLoading={hrQuery.isLoading}
            />
          </div>
        )}
      </div>

      {/* LAYER 3: Drill-Down Diagnostic Sessions History */}
      <SessionHistory sessions={filteredSessions} />
    </div>
  );
}
