import { motion } from "framer-motion";
import { Sparkles, Lightbulb } from "lucide-react";
import Card from "../Common/Card";
import type { AIFeedback } from "../../types";

interface FeedbackSectionProps {
  feedback: AIFeedback[];
}

export default function FeedbackSection({ feedback }: FeedbackSectionProps) {
  const latest = feedback[0];

  return (
    <Card>
      <div className="flex items-center gap-3 mb-4 border-b border-slate-100 pb-4">
        <div className="w-10 h-10 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center">
          <Sparkles className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-slate-900">AI Coaching Feedback</h3>
          <p className="text-xs text-slate-500">
            Adjudicated by local Qwen 3.5 AI evaluator.
          </p>
        </div>
        {latest ? (
          <div className="ml-auto text-right">
            <div className="text-2xl font-black text-violet-600">
              {Math.round(latest.score)}/100
            </div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
              overall score
            </div>
          </div>
        ) : null}
      </div>

      {latest ? (
        <>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="text-slate-800 leading-relaxed text-sm sm:text-base font-normal"
          >
            {latest.content}
          </motion.p>

          {latest.suggestions?.length ? (
            <div className="mt-6 space-y-3">
              <h4 className="text-xs uppercase tracking-wider font-bold text-violet-700 flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-amber-500" /> Action Items &amp; Drills
              </h4>
              <ul className="space-y-2.5">
                {latest.suggestions.map((s, idx) => (
                  <motion.li
                    key={idx}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.1 + idx * 0.08 }}
                    className="flex gap-3 items-start text-sm text-slate-800 bg-slate-50 border border-slate-200/90 rounded-xl px-4 py-3 shadow-xs"
                  >
                    <span className="w-6 h-6 shrink-0 rounded-lg bg-violet-100 text-violet-700 font-bold flex items-center justify-center text-xs">
                      {idx + 1}
                    </span>
                    <span className="leading-relaxed">{s}</span>
                  </motion.li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-slate-500 py-4">
          Feedback will appear after analysis completes.
        </p>
      )}
    </Card>
  );
}
