import { motion } from "framer-motion";
import Card from "../Common/Card";
import type { Transcription } from "../../types";

const UNCONDITIONAL_FILLERS = [
  "um",
  "umm",
  "ummm",
  "uh",
  "uhh",
  "uhhh",
  "uhhhh",
  "hmm",
  "hmmm",
  "er",
  "ah",
  "you know",
  "i mean",
  "kind of",
  "sort of",
  "you see",
  "like i said",
  "to be honest",
  "by the way",
  "at the end of the day",
  "literally",
  "basically",
];

function highlight(text: string) {
  if (!text) return null;

  // Tokenize and evaluate with context
  // Regex matches candidate filler words/phrases + word boundaries
  const pattern =
    /\b(you know|i mean|kind of|sort of|you see|like i said|to be honest|by the way|at the end of the day|um+|uh+|hmm+|er|ah|well|like|right|literally|basically)\b/gi;

  const elements: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    const start = match.index;
    const end = pattern.lastIndex;
    const word = match[0];
    const lowerWord = word.toLowerCase();

    // Push preceding non-filler text
    if (start > lastIndex) {
      elements.push(text.slice(lastIndex, start));
    }

    // Context check for ambiguous words
    const pre = text.slice(Math.max(0, start - 15), start).toLowerCase().trim();
    const post = text.slice(end, Math.min(text.length, end + 15)).toLowerCase().trim();

    let isFiller = true;

    if (lowerWord === "well") {
      // Exclude 'as well as', 'as well', 'very well', 'well known', 'well done'
      if (
        pre.endsWith("as") ||
        post.startsWith("as") ||
        pre.endsWith("very") ||
        pre.endsWith("quite") ||
        post.startsWith("done") ||
        post.startsWith("known")
      ) {
        isFiller = false;
      }
    } else if (lowerWord === "like") {
      // Exclude comparison or verb: 'colour like', 'look like', 'feel like', 'i like', 'we like'
      if (
        /\b(feel|feels|look|looks|sound|sounds|seem|seems|would|i|we|they|colour|color|things|something|such)\s*$/.test(
          pre
        )
      ) {
        isFiller = false;
      }
    } else if (lowerWord === "right") {
      // Exclude 'right now', 'right here', 'all right', 'that's right'
      if (
        pre.endsWith("all") ||
        pre.endsWith("that's") ||
        post.startsWith("now") ||
        post.startsWith("here") ||
        post.startsWith("hand") ||
        post.startsWith("side")
      ) {
        isFiller = false;
      }
    }

    if (isFiller) {
      elements.push(
        <span
          key={start}
          className="bg-rose-100 text-rose-800 border-b-2 border-rose-400 font-semibold rounded px-1 py-0.5"
          title="Detected hesitation / filler sound"
        >
          {word}
        </span>
      );
    } else {
      elements.push(word);
    }

    lastIndex = end;
  }

  if (lastIndex < text.length) {
    elements.push(text.slice(lastIndex));
  }

  return elements;
}

interface TranscriptionViewProps {
  transcription: Transcription | null;
}

export default function TranscriptionView({ transcription }: TranscriptionViewProps) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
        <h3 className="text-lg font-bold text-slate-900">Word-Aligned Transcript</h3>
        {transcription ? (
          <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
            {transcription.language.toUpperCase()} &middot; {Math.round(transcription.confidence * 100)}% accuracy
          </span>
        ) : null}
      </div>
      {transcription ? (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="text-slate-800 leading-relaxed text-sm sm:text-base whitespace-pre-wrap font-normal"
        >
          {highlight(transcription.text)}
        </motion.p>
      ) : (
        <p className="text-slate-500 text-sm">No transcription available yet.</p>
      )}
    </Card>
  );
}
