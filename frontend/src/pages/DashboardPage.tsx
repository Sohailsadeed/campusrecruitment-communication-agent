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

type DashboardQuery = {
  isError: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
};

/**
 * AUTH-C/D-F: these endpoints answer 401 for an expired token and 404 once a row belongs to someone
 * else, and a failed request used to render as "no practice yet". The copy keeps the four cases
 * distinguishable so an outage is never mistaken for an empty history.
 */
function describeDashboardFailure(error: unknown): string {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  if (status === 401) return "Your session has expired. Sign in again to see your own progress.";
  if (status === 403 || status === 404) return "These results are not available for this account.";
  if (typeof status === "number") return `The progress service rejected the request (HTTP ${status}).`;
  return "Your progress could not be fetched. Check your connection and try again.";
}

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

  const failedSections: { label: string; query: DashboardQuery }[] = [
    { label: "Practice summary", query: summaryQuery },
    { label: "Placement readiness matrix", query: readinessQuery },
    { label: "JAM fluency trajectory", query: metricsQuery },
    { label: "Technical trajectory", query: techQuery },
    { label: "Guesstimate trajectory", query: guesstimateQuery },
    { label: "HR trajectory", query: hrQuery },
    { label: "Session history", query: sessionsQuery },
  ].filter((section) => section.query.isError);

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
      {failedSections.length > 0 && (
        <div
          role="alert"
          className="flex flex-col gap-2 rounded-lg border border-error/40 bg-error/5 p-4 text-left"
        >
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-error">cloud_off</span>
            <span className="text-sm font-semibold text-on-surface">
              Some of your progress could not be loaded
            </span>
          </div>
          <ul className="ml-5 list-disc space-y-1 text-[11px] text-on-surface-variant">
            {failedSections.map((section) => (
              <li key={section.label}>
                <span className="font-semibold text-on-surface">{section.label}:</span>{" "}
                {describeDashboardFailure(section.query.error)}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-on-surface-variant">
            The sections below show only what was actually retrieved — an empty chart here means the
            request failed, not that you have no recordings.
          </p>
          <button
            type="button"
            onClick={() => {
              for (const section of failedSections) void section.query.refetch();
            }}
            className="w-fit rounded border border-outline-variant/40 px-2.5 py-1 text-[10px] font-semibold text-on-surface hover:bg-surface-container-high"
          >
            Retry these requests
          </button>
        </div>
      )}

      {!readinessQuery.isError && (
        <PlacementReadinessMatrix
          data={readinessData}
          isLoading={readinessQuery.isLoading}
        />
      )}

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
            {!metricsQuery.isError && <ProgressDashboard metrics={metrics} />}
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
            {!techQuery.isError && (
              <TechnicalProgressDashboard
                data={techData}
                isLoading={techQuery.isLoading}
              />
            )}
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
            {!guesstimateQuery.isError && (
              <GuesstimateProgressDashboard
                data={guesstimateData}
                isLoading={guesstimateQuery.isLoading}
              />
            )}
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
            {!hrQuery.isError && (
              <HRProgressDashboard
                data={hrData}
                isLoading={hrQuery.isLoading}
              />
            )}
          </div>
        )}
      </div>

      {/* LAYER 3: Drill-Down Diagnostic Sessions History */}
      {!sessionsQuery.isError && <SessionHistory sessions={filteredSessions} />}
    </div>
  );
}
