import { Link } from "react-router-dom";
import Card from "../Common/Card";
import type { PlacementReadinessResponse, PlacementReadinessCard } from "../../api/analysis";

interface PlacementReadinessMatrixProps {
  data?: PlacementReadinessResponse;
  isLoading?: boolean;
}

export default function PlacementReadinessMatrix({
  data,
  isLoading,
}: PlacementReadinessMatrixProps) {
  if (isLoading) {
    return (
      <Card>
        <div className="h-64 flex items-center justify-center text-outline text-xs gap-2">
          <span className="material-symbols-outlined animate-spin text-[20px]">sync</span>
          <span>Compiling Multi-Round Placement Telemetry...</span>
        </div>
      </Card>
    );
  }

  const cards: PlacementReadinessCard[] = data?.cards || [];
  const readyCount = data?.ready_count || 0;
  const attemptedCount = data?.attempted_count || 0;
  const totalRounds = data?.total_rounds || 4;

  const getStatusBadge = (status: "ready" | "in_progress" | "not_attempted") => {
    switch (status) {
      case "ready":
        return {
          label: "Tier-1 Validated",
          style: "bg-tertiary/15 text-tertiary border-tertiary/30",
          icon: "verified",
        };
      case "in_progress":
        return {
          label: "Developing",
          style: "bg-secondary/15 text-secondary border-secondary/30",
          icon: "trending_up",
        };
      case "not_attempted":
      default:
        return {
          label: "Unattempted",
          style: "bg-surface-container-highest text-outline border-outline-variant/30",
          icon: "radio_button_unchecked",
        };
    }
  };

  const getTrackIcon = (key: string) => {
    switch (key) {
      case "jam":
        return "sensors";
      case "technical":
        return "terminal";
      case "guesstimate":
        return "query_stats";
      case "hr":
        return "diversity_3";
      default:
        return "smart_toy";
    }
  };

  return (
    <div className="space-y-4">
      {/* Layer 1 Header & Philosophy Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-md">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-label-caps text-xs text-primary font-bold uppercase tracking-wider">
              Layer 1: Unified Placement Radar
            </span>
            <span className="text-outline text-xs">•</span>
            <span className="text-xs text-on-surface-variant font-medium">
              {readyCount} of {totalRounds} Rounds Validated
            </span>
          </div>
          <h2 className="text-lg font-bold text-on-surface">
            Placement Readiness Matrix (4-Round Standard)
          </h2>
          <p className="text-xs text-outline max-w-2xl leading-relaxed">
            {data?.evaluation_rule ||
              "Each round evaluates distinct core placement competencies. We preserve specialized telemetry for each round rather than masking deficits in an arbitrary aggregate average."}
          </p>
        </div>

        {/* Aggregate Readiness Progress Counter */}
        <div className="flex items-center gap-3 self-start sm:self-center shrink-0">
          <div className="flex flex-col text-right">
            <span className="font-label-caps text-[10px] uppercase text-outline font-semibold">
              Round Coverage
            </span>
            <span className="font-label-numeric text-base font-black text-on-surface">
              {attemptedCount} / {totalRounds} Attempted
            </span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 flex items-center justify-center font-bold font-label-numeric text-primary text-lg">
            {Math.round((readyCount / totalRounds) * 100)}%
          </div>
        </div>
      </div>

      {/* 4 Multi-Round Readiness Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {cards.map((card) => {
          const badge = getStatusBadge(card.status);
          const icon = getTrackIcon(card.key);
          const hasAttempts = card.attempt_count > 0;

          return (
            <div
              key={card.key}
              className={`rounded-2xl border p-5 flex flex-col justify-between transition-all duration-200 ${
                card.status === "ready"
                  ? "bg-surface-container-low border-tertiary/30 hover:border-tertiary/50"
                  : card.status === "in_progress"
                  ? "bg-surface-container-low border-secondary/30 hover:border-secondary/50"
                  : "bg-surface-container-lowest/60 border-outline-variant/30 opacity-90"
              }`}
            >
              {/* Card Top: Track Number, Name & Status */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-surface-container-high flex items-center justify-center text-primary">
                      <span className="material-symbols-outlined text-[18px]">{icon}</span>
                    </div>
                    <span className="font-label-caps text-[10px] uppercase text-outline font-bold">
                      {card.track_number}
                    </span>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${badge.style}`}
                  >
                    <span className="material-symbols-outlined text-[12px]">{badge.icon}</span>
                    {badge.label}
                  </span>
                </div>

                <div>
                  <h3 className="font-headline-sm text-sm font-bold text-on-surface leading-tight">
                    {card.title}
                  </h3>
                  <span className="text-[11px] text-outline">
                    {hasAttempts
                      ? `${card.attempt_count} attempt${card.attempt_count > 1 ? "s" : ""} recorded`
                      : "Zero attempts recorded"}
                  </span>
                </div>

                {/* Primary Metric Display or Meaningful Empty State */}
                <div className="py-2 border-y border-outline-variant/20">
                  {hasAttempts && card.primary_metric.value !== null ? (
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-on-surface-variant font-medium">
                        {card.primary_metric.label}:
                      </span>
                      <div className="flex items-baseline gap-1">
                        <span className="font-display-hero text-2xl font-black text-on-surface font-label-numeric">
                          {card.primary_metric.value}
                        </span>
                        <span className="text-xs text-outline font-semibold">
                          {card.primary_metric.unit}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="py-1 text-center flex flex-col items-center justify-center gap-1">
                      <span className="text-xs font-semibold text-outline">No Baseline Recorded</span>
                      <span className="text-[10px] text-outline-variant">Complete round drill to establish telemetry</span>
                    </div>
                  )}
                </div>

                {/* Secondary Telemetry Strip */}
                <div className="space-y-1.5 pt-1">
                  {card.secondary_metrics.map((sec, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-[11px] text-on-surface-variant"
                    >
                      <span className="text-outline">{sec.label}</span>
                      <span className="font-medium text-on-surface font-label-numeric">
                        {sec.value}{" "}
                        <span className="text-[10px] text-outline font-normal">
                          {sec.unit}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Card Footer: Fast Launch CTA or View Diagnostic Link */}
              <div className="pt-4 mt-4 border-t border-outline-variant/20 flex items-center gap-2">
                {card.report_path && (
                  <Link
                    to={card.report_path}
                    className="flex-1 py-1.5 px-3 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-center font-semibold text-xs transition-colors border border-outline-variant/30 flex items-center justify-center gap-1"
                  >
                    <span>Dossier</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_outward</span>
                  </Link>
                )}
                <Link
                  to={card.drill_path}
                  className={`flex-1 py-1.5 px-3 rounded-lg text-center font-bold text-xs transition-all flex items-center justify-center gap-1 ${
                    hasAttempts
                      ? "bg-primary text-on-primary hover:opacity-90 shadow-sm"
                      : "bg-tertiary text-on-tertiary hover:opacity-90 shadow-md shadow-tertiary/20"
                  }`}
                >
                  <span className="material-symbols-outlined text-[14px]">play_arrow</span>
                  <span>{hasAttempts ? "Drill Again" : "Launch Drill"}</span>
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
