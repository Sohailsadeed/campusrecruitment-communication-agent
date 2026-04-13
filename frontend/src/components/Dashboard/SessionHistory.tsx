import { Link } from "react-router-dom";
import { Trash2, ArrowUpRight } from "lucide-react";
import Card from "../Common/Card";
import { useDeleteSession } from "../../hooks/useSessions";
import type { SessionSummary } from "../../types";

interface SessionHistoryProps {
  sessions: SessionSummary[];
}

export default function SessionHistory({ sessions }: SessionHistoryProps) {
  const deleteMutation = useDeleteSession();

  return (
    <Card padding="p-0">
      <div className="p-6 pb-0 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Recent sessions</h3>
        <span className="text-xs text-slate-400">{sessions.length} total</span>
      </div>
      <div className="divide-y divide-white/5 mt-4">
        {sessions.length === 0 ? (
          <p className="text-sm text-slate-400 p-6">
            No sessions yet. Head to the Record page to start.
          </p>
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between px-6 py-4 hover:bg-white/5 transition-colors"
            >
              <div>
                <div className="font-medium text-slate-100">{s.title}</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {new Date(s.created_at).toLocaleString()} &middot;{" "}
                  {Math.round(s.duration_seconds)}s &middot; {s.status}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  to={`/analysis/${s.id}`}
                  className="w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 border border-white/10 hover:bg-primary-500/20 hover:border-primary-500/40 transition-colors"
                  aria-label="Open analysis"
                >
                  <ArrowUpRight className="w-4 h-4" />
                </Link>
                <button
                  onClick={() => deleteMutation.mutate(s.id)}
                  className="w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 border border-white/10 hover:bg-rose-500/20 hover:border-rose-500/40 transition-colors"
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
