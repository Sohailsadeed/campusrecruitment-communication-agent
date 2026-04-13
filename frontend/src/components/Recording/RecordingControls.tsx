import { Circle, Square, RefreshCcw, Upload } from "lucide-react";
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
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div
          className={`w-3 h-3 rounded-full ${
            status === "recording"
              ? "bg-rose-500 animate-pulse"
              : status === "ready"
              ? "bg-emerald-400"
              : "bg-slate-500"
          }`}
        />
        <span className="font-mono text-2xl tracking-wider">
          {formatDuration(elapsedMs)}
        </span>
        <span className="text-xs uppercase tracking-widest text-slate-400">
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
            <Circle className="w-4 h-4 fill-current" /> Start Recording
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
              <Upload className="w-4 h-4" /> Upload &amp; Analyze
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
