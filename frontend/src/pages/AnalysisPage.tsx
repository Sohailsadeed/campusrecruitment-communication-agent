import { useParams, Navigate } from "react-router-dom";
import { useEffect } from "react";
import axios from "axios";
import AnalysisResults from "../components/Analysis/AnalysisResults";
import Loading from "../components/Common/Loading";
import Card from "../components/Common/Card";
import Button from "../components/Common/Button";
import { useAnalyzeSession, useSessionDetail } from "../hooks/useSessions";

/**
 * A refused analysis must read as a refusal. The report component fills absent metrics with
 * defaults, so anything short of a server-confirmed `completed` stays out of it.
 */
function describeAnalysisFailure(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.code === "ECONNABORTED") {
      return "The analysis service timed out. Your recording is saved — try analyzing it again.";
    }
    if (!error.response) {
      return "SpeakFlow could not reach the analysis service. Check your connection and try again.";
    }
    const status = error.response.status;
    if (status === 401) {
      return "Your session has expired, so the recording was not analyzed. Sign in again and retry.";
    }
    if (status === 403 || status === 404) {
      return "This recording is not available for this account, so nothing was analyzed.";
    }
    if (status === 502 || status === 503 || status === 504) {
      return `The analysis service is unavailable right now (HTTP ${status}). Try again shortly.`;
    }
    return `The analysis service rejected the request (HTTP ${status}).`;
  }
  if (error instanceof Error && error.message) {
    return `Analysis failed: ${error.message}`;
  }
  return "Analysis failed for an unknown reason.";
}

export default function AnalysisPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const id = sessionId ? Number(sessionId) : undefined;
  const { data, isLoading, error, refetch } = useSessionDetail(id);
  const analyze = useAnalyzeSession();

  useEffect(() => {
    // Only trigger JAM audio prosody analysis for JAM rounds, not technical round interviews
    if (data && data.round_type !== "technical" && data.status === "pending"
      && !analyze.isPending && !analyze.isError) {
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

  if (analyze.isError) {
    return (
      <Card role="alert" className="space-y-4">
        <p className="text-rose-300">{describeAnalysisFailure(analyze.error)}</p>
        <div className="flex gap-3">
          <Button
            onClick={() => analyze.mutate(data.id)}
            loading={analyze.isPending}
          >
            Try analyzing again
          </Button>
          <Button variant="ghost" onClick={() => refetch()}>
            Reload session
          </Button>
        </div>
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

  if (data.status === "pending") {
    // Reached on the render before the effect above fires, and on a reload while the request is in
    // flight. It is a wait, not a result.
    return <Loading label="Preparing your analysis..." />;
  }

  if (data.status !== "completed") {
    // `in_progress` is a real status for an HR or guesstimate round, and any other value means the
    // analysis never recorded one. AnalysisResults would fill the gap with defaults, so no report
    // is shown until the server says `completed`; the run stays user-initiated here.
    return (
      <Card role="alert" className="space-y-4">
        <p className="text-rose-300">
          This session has no finished analysis to show yet, so there are no results to report.
        </p>
        <Button onClick={() => analyze.mutate(data.id)} loading={analyze.isPending}>
          Analyze now
        </Button>
      </Card>
    );
  }

  return <AnalysisResults session={data} />;
}
