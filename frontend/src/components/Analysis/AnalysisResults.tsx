import { motion } from "framer-motion";
import TranscriptionView from "./TranscriptionView";
import MetricsChart from "./MetricsChart";
import FeedbackSection from "./FeedbackSection";
import type { SessionDetail } from "../../types";

interface AnalysisResultsProps {
  session: SessionDetail;
}

export default function AnalysisResults({ session }: AnalysisResultsProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="space-y-6"
    >
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{session.title}</h1>
          {session.description ? (
            <p className="text-slate-400 mt-1">{session.description}</p>
          ) : null}
          <div className="flex gap-4 mt-2 text-xs text-slate-500">
            <span>Status: {session.status}</span>
            <span>Duration: {Math.round(session.duration_seconds)}s</span>
          </div>
        </div>
      </div>

      <MetricsChart analysis={session.analysis} />
      <FeedbackSection feedback={session.feedback} />
      <TranscriptionView transcription={session.transcription} />
    </motion.div>
  );
}
