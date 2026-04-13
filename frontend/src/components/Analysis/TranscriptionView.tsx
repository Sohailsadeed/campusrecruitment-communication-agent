import { motion } from "framer-motion";
import Card from "../Common/Card";
import type { Transcription } from "../../types";

const FILLERS = [
  "um",
  "uh",
  "like",
  "you know",
  "basically",
  "literally",
  "actually",
  "so",
  "well",
  "i mean",
  "right",
  "okay",
];

function highlight(text: string) {
  const escaped = FILLERS.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const regex = new RegExp(`\\b(${escaped})\\b`, "gi");
  const parts = text.split(regex);
  return parts.map((part, idx) =>
    regex.test(part) ? (
      <span
        key={idx}
        className="bg-rose-500/20 text-rose-200 rounded px-1 py-0.5"
      >
        {part}
      </span>
    ) : (
      <span key={idx}>{part}</span>
    )
  );
}

interface TranscriptionViewProps {
  transcription: Transcription | null;
}

export default function TranscriptionView({ transcription }: TranscriptionViewProps) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Transcription</h3>
        {transcription ? (
          <span className="text-xs uppercase tracking-wider text-slate-400">
            {transcription.language} &middot; {Math.round(transcription.confidence * 100)}% conf
          </span>
        ) : null}
      </div>
      {transcription ? (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="text-slate-100 leading-relaxed whitespace-pre-wrap"
        >
          {highlight(transcription.text)}
        </motion.p>
      ) : (
        <p className="text-slate-400 text-sm">No transcription available yet.</p>
      )}
    </Card>
  );
}
