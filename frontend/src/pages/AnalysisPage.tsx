import { useParams, Navigate } from "react-router-dom";
import { useEffect } from "react";
import AnalysisResults from "../components/Analysis/AnalysisResults";
import Loading from "../components/Common/Loading";
import Card from "../components/Common/Card";
import Button from "../components/Common/Button";
import { useAnalyzeSession, useSessionDetail } from "../hooks/useSessions";

export default function AnalysisPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const id = sessionId ? Number(sessionId) : undefined;
  const { data, isLoading, error } = useSessionDetail(id);
  const analyze = useAnalyzeSession();

  useEffect(() => {
    // Only trigger JAM audio prosody analysis for JAM rounds, not technical round interviews
    if (data && data.round_type !== "technical" && data.status === "pending" && !analyze.isPending) {
      analyze.mutate(data.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.id, data?.round_type]);

  if (isLoading) return <Loading label="Loading session" />;

  // Dedicated routing: technical interviews render the Technical Dossier Report
  if (data?.round_type === "technical") {
    return <Navigate to={`/technical/report/${data.id}`} replace />;
  }
  if (error || !data) {
    return (
      <Card>
        <p className="text-rose-300">
          Failed to load session. It may have been deleted.
        </p>
      </Card>
    );
  }

  if (data.status === "processing" || analyze.isPending) {
    return <Loading label="Analyzing your session..." />;
  }

  if (data.status === "failed") {
    return (
      <Card className="space-y-4">
        <p className="text-rose-300">Analysis failed for this session.</p>
        <Button onClick={() => analyze.mutate(data.id)} loading={analyze.isPending}>
          Retry analysis
        </Button>
      </Card>
    );
  }

  return <AnalysisResults session={data} />;
}
