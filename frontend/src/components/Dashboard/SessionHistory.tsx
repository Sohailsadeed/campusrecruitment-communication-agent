import { Link } from "react-router-dom";
import { Trash2, ArrowUpRight } from "lucide-react";
import Card from "../Common/Card";
import { useDeleteSession } from "../../hooks/useSessions";
import type { SessionSummary } from "../../types";

interface SessionHistoryProps {
  sessions: SessionSummary[];
}

function StatusBadge({ status }: { status: string }) {
  if (status === "completed") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-tertiary/15 text-tertiary border border-tertiary/30">
        <span className="w-1.5 h-1.5 rounded-full bg-tertiary" />
        Completed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-secondary-container/20 text-secondary border border-secondary/30">
      <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
      {status === "pending" ? "Pending Analysis" : status}
    </span>
  );
}

export default function SessionHistory({ sessions }: SessionHistoryProps) {
  const deleteMutation = useDeleteSession();

  return (
    <Card padding="p-0">
      <div className="p-6 pb-4 flex items-center justify-between border-b border-outline-variant/30">
        <div>
          <h3 className="text-lg font-bold text-on-surface">Recent Sessions</h3>
          <p className="text-xs text-outline mt-0.5">Your recorded JAM practice rounds</p>
        </div>
        <span className="text-xs font-semibold text-primary bg-surface-container-high border border-primary/20 px-2.5 py-1 rounded-full">
          {sessions.length} total
        </span>
      </div>
      <div className="divide-y divide-outline-variant/20">
        {sessions.length === 0 ? (
          <p className="text-sm text-outline p-8 text-center">
            No sessions yet. Head to the{" "}
            <Link to="/record" className="text-primary font-semibold underline">
              Practice Arena
            </Link>{" "}
            to start your first 60-second take.
          </p>
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between px-6 py-4 hover:bg-surface-container/60 transition-colors"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2.5">
                  <span className="font-semibold text-on-surface text-sm sm:text-base">{s.title}</span>
                  {s.round_type === "technical" && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-primary/10 text-primary border border-primary/25 uppercase tracking-wider">
                      Technical
                    </span>
                  )}
                  {s.round_type === "guesstimate" && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-tertiary/15 text-tertiary border border-tertiary/30 uppercase tracking-wider">
                      Guesstimate
                    </span>
                  )}
                  {s.round_type === "hr" && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-primary/15 text-primary border border-primary/30 uppercase tracking-wider">
                      HR Behavioral
                    </span>
                  )}
                  <StatusBadge status={s.status} />
                </div>
                <div className="text-xs text-outline">
                  {new Date(s.created_at).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}{" "}
                  &middot;{" "}
                  <span className="font-medium text-secondary">
                    {Math.round(s.duration_seconds)}s
                  </span>{" "}
                  {s.round_type === "technical" || s.round_type === "guesstimate" || s.round_type === "hr" ? "drill" : "take"}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {s.status === "in_progress" ? (
                  <Link
                    to={
                      s.round_type === "hr"
                        ? `/hr/${s.id}`
                        : s.round_type === "guesstimate"
                        ? `/guesstimate/${s.id}`
                        : s.round_type === "technical"
                        ? `/technical/${s.id}`
                        : `/record?session_id=${s.id}`
                    }
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary text-on-secondary font-bold text-xs hover:bg-secondary/90 transition-all shadow-sm"
                  >
                    Resume Drill <ArrowUpRight className="w-3.5 h-3.5" />
                  </Link>
                ) : (
                  <Link
                    to={
                      s.round_type === "hr"
                        ? `/hr/report/${s.id}`
                        : s.round_type === "guesstimate"
                        ? `/guesstimate/report/${s.id}`
                        : s.round_type === "technical"
                        ? `/technical/report/${s.id}`
                        : `/analysis/${s.id}`
                    }
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container-high text-primary border border-primary/20 hover:bg-primary hover:text-on-primary font-medium text-xs transition-colors"
                  >
                    View Report <ArrowUpRight className="w-3.5 h-3.5" />
                  </Link>
                )}
                <button
                  onClick={() => deleteMutation.mutate(s.id)}
                  className="w-8 h-8 flex items-center justify-center rounded-lg text-outline hover:text-error hover:bg-error-container/20 transition-colors"
                  aria-label="Delete session"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}

