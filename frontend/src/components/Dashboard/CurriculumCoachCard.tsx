import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Card from "../Common/Card";
import {
  getActiveCurriculumPlan,
  generateCurriculumPlan,
  completeCurriculumDay,
  autoSyncCurriculumDrills,
} from "../../api/coach";
import type { CurriculumPlan, CurriculumDay, CurriculumBottleneck } from "../../types/coach";

const TARGET_ROLES = [
  "General Placement",
  "Strategy & Management Consultant",
  "Software Engineer (Tier-1 Systems)",
  "Product Manager (Tech)",
  "Data & AI Engineer",
];

export default function CurriculumCoachCard() {
  const [plan, setPlan] = useState<CurriculumPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [selectedRole, setSelectedRole] = useState(TARGET_ROLES[0]);
  const [selectedDayNumber, setSelectedDayNumber] = useState<number>(1);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const fetchPlan = async () => {
    try {
      setLoading(true);
      const res = await getActiveCurriculumPlan();
      if (res.has_plan && res.plan) {
        setPlan(res.plan);
        setSelectedRole(res.plan.target_role || TARGET_ROLES[0]);
        // Set selected day to the first in_progress day
        const activeDay = res.plan.days.find((d) => d.status === "in_progress") || res.plan.days[0];
        if (activeDay) {
          setSelectedDayNumber(activeDay.day_number);
        }
      } else {
        setPlan(null);
      }
    } catch (err) {
      console.error("Failed to fetch curriculum plan:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlan();
  }, []);

  const handleGenerate = async (force: boolean = false) => {
    try {
      setIsGenerating(true);
      setSyncMessage(null);
      const res = await generateCurriculumPlan({
        target_role: selectedRole,
        force_replan: force,
      });
      if (res.plan) {
        setPlan(res.plan);
        const activeDay = res.plan.days.find((d) => d.status === "in_progress") || res.plan.days[0];
        if (activeDay) {
          setSelectedDayNumber(activeDay.day_number);
        }
      }
    } catch (err) {
      console.error("Failed to generate plan:", err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleMarkComplete = async (dayNumber: number) => {
    if (!plan) return;
    try {
      const res = await completeCurriculumDay({
        plan_id: plan.id,
        day_number: dayNumber,
      });
      if (res.success) {
        await fetchPlan();
      }
    } catch (err) {
      console.error("Failed to complete day:", err);
    }
  };

  const handleAutoSync = async () => {
    try {
      setIsSyncing(true);
      setSyncMessage(null);
      const res = await autoSyncCurriculumDrills();
      if (res.synced) {
        setSyncMessage(`Day ${res.completed_day} auto-completed! Score: ${res.score_achieved ?? "Verified"}`);
        await fetchPlan();
      } else {
        setSyncMessage(res.message || "No new completed sessions matching current day.");
      }
    } catch (err) {
      console.error("Failed to auto-sync drills:", err);
      setSyncMessage("Sync error. Please try again.");
    } finally {
      setIsSyncing(false);
      setTimeout(() => setSyncMessage(null), 4000);
    }
  };

  const getRoundBadge = (round: string) => {
    switch (round) {
      case "guesstimate":
        return { label: "Consulting Sizing", icon: "query_stats", color: "text-tertiary bg-tertiary/10 border-tertiary/30" };
      case "technical":
        return { label: "Technical Arch", icon: "terminal", color: "text-secondary bg-secondary/10 border-secondary/30" };
      case "jam":
        return { label: "JAM Fluency", icon: "sensors", color: "text-primary bg-primary/10 border-primary/30" };
      case "hr":
      default:
        return { label: "HR Leadership", icon: "diversity_3", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" };
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="h-48 flex items-center justify-center text-outline text-xs gap-2">
          <span className="material-symbols-outlined animate-spin text-[20px]">sync</span>
          <span>Curriculum Coach analyzing historical session telemetry...</span>
        </div>
      </Card>
    );
  }

  // Empty state: No active plan yet
  if (!plan) {
    return (
      <Card className="border-secondary/30 bg-gradient-to-br from-surface-container-low via-surface-container to-surface-container-low relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6 p-2">
          <div className="space-y-2 max-w-xl">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-secondary/15 text-secondary border border-secondary/30 font-label-numeric-sm text-[11px] font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
              LangGraph Autonomous Agent
            </div>
            <h2 className="text-xl font-bold text-on-surface">
              Autonomous Curriculum Coach
            </h2>
            <p className="text-sm text-on-surface-variant leading-relaxed">
              Synthesize an adaptive 7-day interview syllabus grounded in your cross-round metrics from JAM, Technical, Guesstimate, and HR sessions.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value)}
              className="px-3.5 py-2 rounded-lg bg-surface-container-high border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-secondary"
            >
              {TARGET_ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>

            <button
              onClick={() => handleGenerate(false)}
              disabled={isGenerating}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-secondary text-on-secondary font-semibold text-xs shadow-md hover:opacity-90 transition-all disabled:opacity-50"
            >
              {isGenerating ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-[16px]">sync</span>
                  <span>Synthesizing Plan...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[16px]">auto_awesome</span>
                  <span>Synthesize 7-Day Roadmap</span>
                </>
              )}
            </button>
          </div>
        </div>
      </Card>
    );
  }

  // Active Plan Display
  const days: CurriculumDay[] = plan.days || [];
  const activeDay = days.find((d) => d.day_number === selectedDayNumber) || days[0];
  const completedCount = days.filter((d) => d.status === "completed").length;
  const progressPercent = Math.round((completedCount / days.length) * 100);
  const bottlenecks: CurriculumBottleneck[] = plan.identified_bottlenecks || [];

  return (
    <Card className="border-secondary/30 bg-surface-container-low relative overflow-hidden shadow-xl">
      {/* Glow highlight */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-secondary/5 rounded-full blur-3xl pointer-events-none" />

      {/* Header section */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 pb-6 border-b border-outline-variant/20">
        <div>
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-secondary/15 text-secondary border border-secondary/30 font-label-numeric-sm text-[11px] font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
              LangGraph Autonomous Agent
            </span>
            <span className="px-2.5 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-label-numeric-sm text-[11px] border border-outline-variant/30">
              Role: <strong className="text-on-surface">{plan.target_role}</strong>
            </span>
            <span className="px-2.5 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-label-numeric-sm text-[11px] border border-outline-variant/30">
              Progress: <strong className="text-secondary">{completedCount} of 7 Days ({progressPercent}%)</strong>
            </span>
          </div>
          <h2 className="text-xl font-bold text-on-surface tracking-tight">
            {plan.roadmap_title}
          </h2>
          <p className="text-xs text-on-surface-variant mt-1">
            Autonomous daily calibration prioritizing high-severity placement bottlenecks detected across your historical interview sessions.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 flex-wrap self-start lg:self-auto">
          {syncMessage && (
            <span className="text-xs font-medium text-secondary animate-fade-in bg-secondary/10 px-2.5 py-1 rounded-md border border-secondary/20">
              {syncMessage}
            </span>
          )}

          <button
            onClick={handleAutoSync}
            disabled={isSyncing}
            title="Auto-detect recently completed session matching today's drill"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/40 text-on-surface text-xs font-semibold transition-colors disabled:opacity-50"
          >
            <span className={`material-symbols-outlined text-[15px] text-tertiary ${isSyncing ? "animate-spin" : ""}`}>
              sync
            </span>
            <span>Sync Latest</span>
          </button>

          <button
            onClick={() => handleGenerate(true)}
            disabled={isGenerating}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-secondary text-on-secondary hover:opacity-90 text-xs font-semibold shadow-sm transition-all disabled:opacity-50"
          >
            <span className={`material-symbols-outlined text-[15px] ${isGenerating ? "animate-spin" : ""}`}>
              refresh
            </span>
            <span>{isGenerating ? "Re-Planning..." : "Re-Plan Roadmap"}</span>
          </button>
        </div>
      </div>

      {/* Diagnosed Bottlenecks Strip */}
      {bottlenecks.length > 0 && (
        <div className="py-4 border-b border-outline-variant/20">
          <div className="text-[11px] font-semibold text-outline tracking-wider uppercase mb-2 flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[15px] text-secondary">troubleshoot</span>
            <span>Diagnosed Bottlenecks from Progress Telemetry</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {bottlenecks.slice(0, 3).map((b, idx) => (
              <div
                key={idx}
                className="p-2.5 rounded-lg bg-surface-container-high/60 border border-outline-variant/30 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="text-xs font-bold text-on-surface truncate">
                      {b.dimension}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${
                        b.severity === "high"
                          ? "bg-error/15 text-error border border-error/30"
                          : "bg-tertiary/15 text-tertiary border border-tertiary/30"
                      }`}
                    >
                      {b.severity}
                    </span>
                  </div>
                  <p className="text-[11px] text-on-surface-variant line-clamp-2 leading-relaxed">
                    {b.reason}
                  </p>
                </div>
                <div className="mt-2 pt-1.5 border-t border-outline-variant/20 text-[10px] text-outline font-medium">
                  Goal: <span className="text-on-surface">{b.target_metric}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Spotlight Card */}
      {activeDay && (
        <div className="my-5 p-4 sm:p-5 rounded-xl bg-gradient-to-r from-surface-container to-surface-container-high border border-outline-variant/40 shadow-inner">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-secondary/20 text-secondary border border-secondary/30">
                Day {activeDay.day_number} Focus
              </span>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border ${
                  getRoundBadge(activeDay.round_type).color
                }`}
              >
                <span className="material-symbols-outlined text-[13px]">
                  {getRoundBadge(activeDay.round_type).icon}
                </span>
                <span>{getRoundBadge(activeDay.round_type).label}</span>
              </span>
              <span
                className={`text-[11px] px-2 py-0.5 rounded font-semibold ${
                  activeDay.status === "completed"
                    ? "bg-tertiary/15 text-tertiary"
                    : activeDay.status === "in_progress"
                    ? "bg-secondary/15 text-secondary animate-pulse"
                    : "bg-surface-container-highest text-outline"
                }`}
              >
                {activeDay.status === "completed"
                  ? "✓ Completed"
                  : activeDay.status === "in_progress"
                  ? "● Active Drill"
                  : "Upcoming"}
              </span>
            </div>

            {/* Score achieved badge if completed */}
            {activeDay.score_achieved != null && (
              <span className="text-xs font-bold text-tertiary bg-tertiary/10 px-2.5 py-1 rounded-md border border-tertiary/30">
                Score Achieved: {activeDay.score_achieved}/100
              </span>
            )}
          </div>

          <h3 className="text-base sm:text-lg font-bold text-on-surface mb-1">
            {activeDay.title}
          </h3>
          <p className="text-xs text-on-surface-variant leading-relaxed max-w-3xl mb-4">
            {activeDay.pedagogical_rationale}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4 text-xs">
            <div className="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/30">
              <span className="text-[11px] text-outline block">Focus Dimension</span>
              <span className="font-semibold text-on-surface">{activeDay.focus_dimension}</span>
            </div>
            <div className="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/30">
              <span className="text-[11px] text-outline block">Target Metric Goal</span>
              <span className="font-semibold text-on-surface text-secondary">{activeDay.target_metric_goal}</span>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center gap-3 flex-wrap">
            <Link
              to={activeDay.drill_route}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary font-bold text-xs shadow-md hover:opacity-90 transition-all"
            >
              <span className="material-symbols-outlined text-[16px]">play_arrow</span>
              <span>Launch Prescribed Drill ({activeDay.drill_route})</span>
            </Link>

            {activeDay.status !== "completed" && (
              <button
                onClick={() => handleMarkComplete(activeDay.day_number)}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/40 text-on-surface font-semibold text-xs transition-colors"
              >
                <span className="material-symbols-outlined text-[16px] text-tertiary">check_circle</span>
                <span>Mark as Done</span>
              </button>
            )}
          </div>
        </div>
      )}

      {/* 7-Day Timeline Bar */}
      <div>
        <div className="text-[11px] font-semibold text-outline tracking-wider uppercase mb-2 flex items-center justify-between">
          <span>7-Day Progression Timeline</span>
          <span className="text-secondary font-label-numeric-sm">Click day to view briefing</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
          {days.map((d) => {
            const isSelected = d.day_number === selectedDayNumber;
            const badge = getRoundBadge(d.round_type);
            return (
              <button
                key={d.day_number}
                onClick={() => setSelectedDayNumber(d.day_number)}
                className={`p-2.5 rounded-xl border text-left transition-all flex flex-col justify-between ${
                  isSelected
                    ? "bg-surface-container-highest border-secondary shadow-md ring-1 ring-secondary/50"
                    : d.status === "completed"
                    ? "bg-surface-container-high/40 border-tertiary/40 hover:border-tertiary"
                    : d.status === "in_progress"
                    ? "bg-secondary/10 border-secondary/40 hover:border-secondary"
                    : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/40 opacity-75"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-bold text-outline">
                      Day {d.day_number}
                    </span>
                    <span className="text-[11px]">
                      {d.status === "completed" ? (
                        <span className="material-symbols-outlined text-[14px] text-tertiary">check_circle</span>
                      ) : d.status === "in_progress" ? (
                        <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
                      ) : (
                        <span className="material-symbols-outlined text-[13px] text-outline">lock</span>
                      )}
                    </span>
                  </div>
                  <div className="text-xs font-bold text-on-surface line-clamp-1">
                    {d.title.replace(/^Day \d+:\s*/, "")}
                  </div>
                </div>

                <div className="mt-2 pt-1 border-t border-outline-variant/20 flex items-center justify-between text-[10px]">
                  <span className={`px-1 py-0.2 rounded font-medium ${badge.color}`}>
                    {d.round_type.toUpperCase()}
                  </span>
                  {d.score_achieved != null && (
                    <span className="font-bold text-tertiary">{d.score_achieved}</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
