export type RoundType = "jam" | "technical" | "guesstimate" | "hr";

export type DayStatus = "pending" | "in_progress" | "completed";

export interface CurriculumDay {
  day_number: number;
  title: string;
  round_type: RoundType;
  drill_route: string;
  drill_params: Record<string, any>;
  focus_dimension: string;
  pedagogical_rationale: string;
  target_metric_goal: string;
  status: DayStatus;
  completed_at?: string | null;
  score_achieved?: number | null;
}

export interface CurriculumBottleneck {
  dimension: string;
  round: string;
  severity: "high" | "medium" | "low";
  reason: string;
  target_metric: string;
}

export interface CurriculumPlan {
  id: number;
  target_role: string;
  roadmap_title: string;
  status: "active" | "completed" | "archived";
  target_date?: string | null;
  identified_bottlenecks: CurriculumBottleneck[];
  days: CurriculumDay[];
  meta_summary: {
    focus_areas?: string[];
    history_snapshot?: {
      jam_sessions?: number;
      tech_sessions?: number;
      guesstimate_sessions?: number;
      hr_sessions?: number;
    };
  };
  created_at: string;
  updated_at: string;
}

export interface ActivePlanResponse {
  has_plan: boolean;
  plan: CurriculumPlan | null;
}

export interface GeneratePlanResponse {
  has_plan: boolean;
  reused_existing?: boolean;
  plan: CurriculumPlan;
}
