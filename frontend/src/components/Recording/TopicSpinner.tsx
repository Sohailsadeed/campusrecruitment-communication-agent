import { useState } from "react";
import { Sparkles, Dices, RefreshCw } from "lucide-react";
import topicsData from "../../data/topics.json";

interface TopicSpinnerProps {
  topic: string;
  onTopicChange: (newTopic: string) => void;
  disabled?: boolean;
}

const categories = ["Random", ...Object.keys(topicsData)] as const;

export default function TopicSpinner({
  topic,
  onTopicChange,
  disabled = false,
}: TopicSpinnerProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>("Random");
  const [isSpinning, setIsSpinning] = useState<boolean>(false);

  function getTopicsForCategory(cat: string): string[] {
    if (cat === "Random") {
      return Object.values(topicsData).flat();
    }
    return (topicsData as Record<string, string[]>)[cat] || [];
  }

  function handleSpin() {
    if (disabled || isSpinning) return;
    setIsSpinning(true);

    const pool = getTopicsForCategory(selectedCategory);
    let count = 0;
    const maxSpins = 20;

    const interval = setInterval(() => {
      const randomTopic = pool[Math.floor(Math.random() * pool.length)];
      onTopicChange(randomTopic);
      count++;
      if (count >= maxSpins) {
        clearInterval(interval);
        const finalTopic = pool[Math.floor(Math.random() * pool.length)];
        onTopicChange(finalTopic);
        setIsSpinning(false);
      }
    }, 70);
  }

  return (
    <div className="rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-lg p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <label className="text-xs uppercase tracking-wider font-bold text-primary flex items-center gap-1.5 font-label-caps">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          Choose JAM Topic (Pitch-Perfect Mode)
        </label>

        {/* Category Select */}
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          disabled={disabled || isSpinning}
          className="bg-surface-container border border-outline-variant/40 text-xs rounded-lg px-3 py-1.5 text-on-surface font-medium focus:outline-none focus:ring-1 focus:ring-primary"
        >
          {categories.map((cat) => (
            <option key={cat} value={cat} className="bg-surface-container text-on-surface">
              {cat}
            </option>
          ))}
        </select>
      </div>

      {/* Topic Display Box */}
      <div
        className={`relative min-h-[58px] rounded-xl px-4 py-3 border flex items-center justify-between gap-3 transition-all ${
          isSpinning
            ? "border-secondary bg-secondary-container/20 shadow-sm animate-pulse"
            : "border-outline-variant/40 bg-surface-container"
        }`}
      >
        <span
          className={`text-sm font-semibold transition-all ${
            isSpinning
              ? "text-secondary blur-[0.3px]"
              : "text-on-surface"
          }`}
        >
          {topic || "Select category & spin, or type below..."}
        </span>

        {/* Spin Topic Button */}
        <button
          type="button"
          onClick={handleSpin}
          disabled={disabled || isSpinning}
          className={`shrink-0 flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold shadow-md transition-all ${
            isSpinning
              ? "bg-primary-container text-on-primary-container cursor-not-allowed opacity-75"
              : "bg-primary text-on-primary hover:bg-primary-fixed-dim hover:scale-[1.02] active:scale-[0.98]"
          }`}
        >
          {isSpinning ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Rolling...
            </>
          ) : (
            <>
              <Dices className="w-3.5 h-3.5" /> Spin Topic
            </>
          )}
        </button>
      </div>

      {/* Custom Topic Input */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center text-[11px] text-outline font-medium">
          <span>Or customize your topic:</span>
          <span>Sent directly to AI Adjudicator</span>
        </div>
        <input
          type="text"
          value={topic}
          onChange={(e) => onTopicChange(e.target.value)}
          disabled={disabled || isSpinning}
          placeholder="e.g. Is artificial intelligence making humans obsolete?"
          className="w-full rounded-lg bg-surface-container border border-outline-variant/40 px-3.5 py-2 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary transition-colors font-medium"
        />
      </div>
    </div>
  );
}
