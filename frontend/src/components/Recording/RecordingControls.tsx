import { Circle, Square, RefreshCcw, Upload, Clock, Award } from "lucide-react";
import Button from "../Common/Button";
import type { RecorderStatus } from "../../hooks/useMediaRecorder";

interface RecordingControlsProps {
  status: RecorderStatus;
  elapsedMs: number;
  onInit: () => void;
  onStart: () => void;
  onStop: () => void;
  onReset: () => void;
  onUpload: () => void;
  uploading: boolean;
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const s = (totalSeconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function RecordingControls({
  status,
  elapsedMs,
  onInit,
  onStart,
  onStop,
  onReset,
  onUpload,
  uploading,
}: RecordingControlsProps) {
  const seconds = elapsedMs / 1000;
  const targetPct = Math.min(100, (seconds / 60) * 100);

  // JAM Target Status
  const inZone = seconds >= 45 && seconds <= 60;
  const overTime = seconds > 60;

  return (
    <div className="space-y-4">
      {/* 60s JAM Progress Bar */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="flex items-center gap-1.5 font-semibold text-slate-700">
            <Clock className="w-3.5 h-3.5 text-violet-600" />
            JAM Target: 60 Seconds
          </span>
          <span
            className={`font-semibold ${
              overTime
                ? "text-amber-600 animate-pulse font-bold"
                : inZone
                ? "text-emerald-600 font-bold"
                : "text-slate-500"
            }`}
          >
            {overTime ? "Over 60s!" : inZone ? "Golden Zone (45-60s)" : `${Math.round(seconds)}s / 60s`}
          </span>
        </div>
        <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden border border-slate-200 relative">
          {/* 45s-60s Target Zone Marker */}
          <div className="absolute left-[75%] right-0 top-0 bottom-0 bg-emerald-500/20 border-l border-emerald-500/50 pointer-events-none" />
          <div
            className={`h-full transition-all duration-200 rounded-full ${
              overTime
                ? "bg-amber-500"
                : inZone
                ? "bg-emerald-500 shadow-xs"
                : "bg-violet-600"
            }`}
            style={{ width: `${targetPct}%` }}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
        <div className="flex items-center gap-3">
          <div
            className={`w-3 h-3 rounded-full ${
              status === "recording"
                ? "bg-rose-500 animate-pulse"
                : status === "ready"
                ? "bg-emerald-500"
                : "bg-slate-400"
            }`}
          />
          <span className="font-mono text-2xl tracking-wider font-bold text-slate-900">
            {formatDuration(elapsedMs)}
          </span>
          <span className="text-xs uppercase tracking-widest text-slate-500 font-semibold">
            {status}
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {status === "idle" || status === "error" ? (
            <Button onClick={onInit}>
              <Circle className="w-4 h-4" /> Enable Camera
            </Button>
          ) : null}
          {status === "ready" ? (
            <Button onClick={onStart}>
              <Circle className="w-4 h-4 fill-current text-rose-400" /> Start 60s Take
            </Button>
          ) : null}
          {status === "recording" ? (
            <Button variant="danger" onClick={onStop}>
              <Square className="w-4 h-4 fill-current" /> Stop
            </Button>
          ) : null}
          {status === "stopped" ? (
            <>
              <Button variant="ghost" onClick={onReset}>
                <RefreshCcw className="w-4 h-4" /> Retake
              </Button>
              <Button onClick={onUpload} loading={uploading}>
                <Award className="w-4 h-4 text-amber-300" /> Evaluate JAM Round
              </Button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
