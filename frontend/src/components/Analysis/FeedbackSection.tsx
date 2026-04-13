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
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-400 to-primary-700 flex items-center justify-center">
          <Sparkles className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="text-lg font-semibold">AI Coaching Feedback</h3>
          <p className="text-xs text-slate-400">
            Powered by your configured local LLM.
          </p>
        </div>
        {latest ? (
          <div className="ml-auto text-right">
            <div className="text-2xl font-bold text-primary-200">
              {Math.round(latest.score)}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400">
              overall
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
            className="text-slate-200 leading-relaxed"
          >
            {latest.content}
          </motion.p>

          {latest.suggestions?.length ? (
            <div className="mt-6 space-y-3">
              <h4 className="text-xs uppercase tracking-wider text-primary-300 flex items-center gap-2">
                <Lightbulb className="w-3.5 h-3.5" /> Action items
              </h4>
              <ul className="space-y-2">
                {latest.suggestions.map((s, idx) => (
                  <motion.li
                    key={idx}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.1 + idx * 0.08 }}
                    className="flex gap-3 items-start text-sm text-slate-200 bg-white/5 border border-white/10 rounded-xl px-4 py-3"
                  >
                    <span className="w-6 h-6 shrink-0 rounded-lg bg-primary-500/20 text-primary-200 flex items-center justify-center text-xs font-semibold">
                      {idx + 1}
                    </span>
                    {s}
                  </motion.li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-slate-400">
          Feedback will appear after analysis completes.
        </p>
      )}
    </Card>
  );
}
