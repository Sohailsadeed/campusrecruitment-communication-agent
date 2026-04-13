import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import Card from "../Common/Card";
import VideoPreview from "./VideoPreview";
import FaceTrackingOverlay from "./FaceTrackingOverlay";
import RecordingControls from "./RecordingControls";
import { useMediaRecorder } from "../../hooks/useMediaRecorder";
import { useFaceTracking } from "../../hooks/useFaceTracking";
import { useAnalyzeSession, useUploadSession } from "../../hooks/useSessions";

export default function RecordingSession() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const navigate = useNavigate();
  const recorder = useMediaRecorder();
  const uploadMutation = useUploadSession();
  const analyzeMutation = useAnalyzeSession();

  const [title, setTitle] = useState("Practice Session");
  const [description, setDescription] = useState("");

  const faceState = useFaceTracking(
    videoRef,
    recorder.status === "recording" || recorder.status === "ready"
  );

  const isUploading = uploadMutation.isPending || analyzeMutation.isPending;

  async function handleUpload() {
    if (!recorder.videoBlob) return;
    const session = await uploadMutation.mutateAsync({
      title: title.trim() || "Practice Session",
      description: description.trim() || undefined,
      durationSeconds: recorder.elapsedMs / 1000,
      videoBlob: recorder.videoBlob,
    });
    await analyzeMutation.mutateAsync(session.id);
    recorder.reset();
    navigate(`/analysis/${session.id}`);
  }

  return (
    <div className="grid lg:grid-cols-[1.6fr_1fr] gap-6">
      <Card>
        <div className="relative">
          <VideoPreview
            ref={videoRef}
            stream={
              recorder.status === "recording" || recorder.status === "ready"
                ? recorder.stream
                : null
            }
            src={
              recorder.status === "stopped" && recorder.videoUrl
                ? recorder.videoUrl
                : undefined
            }
            muted={recorder.status !== "stopped"}
          />
          {recorder.status === "ready" || recorder.status === "recording" ? (
            <FaceTrackingOverlay
              faceDetected={faceState.faceDetected}
              centered={faceState.centered}
            />
          ) : null}
        </div>

        <div className="mt-5">
          <RecordingControls
            status={recorder.status}
            elapsedMs={recorder.elapsedMs}
            onInit={recorder.init}
            onStart={recorder.start}
            onStop={recorder.stop}
            onReset={recorder.reset}
            onUpload={handleUpload}
            uploading={isUploading}
          />
          {recorder.error ? (
            <p className="mt-4 text-sm text-rose-300">{recorder.error}</p>
          ) : null}
        </div>
      </Card>

      <Card>
        <motion.div
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          className="space-y-5"
        >
          <h2 className="text-xl font-semibold tracking-tight">Session details</h2>
          <div className="space-y-1.5">
            <label className="block text-xs uppercase tracking-wide text-slate-400">
              Title
            </label>
            <input
              className="w-full rounded-xl bg-black/30 border border-white/10 px-4 py-2.5 text-sm focus:outline-none focus:border-primary-500/60"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Elevator pitch draft"
            />
          </div>
          <div className="space-y-1.5">
            <label className="block text-xs uppercase tracking-wide text-slate-400">
              Description
            </label>
            <textarea
              className="w-full rounded-xl bg-black/30 border border-white/10 px-4 py-2.5 text-sm min-h-[96px] focus:outline-none focus:border-primary-500/60"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What are you practicing today?"
            />
          </div>
          <div className="border-t border-white/10 pt-5 text-xs text-slate-400 leading-relaxed">
            Tip: aim for 130-160 words per minute, keep your shoulders back, and
            look straight into the lens as if it were a listener.
          </div>
        </motion.div>
      </Card>
    </div>
  );
}
