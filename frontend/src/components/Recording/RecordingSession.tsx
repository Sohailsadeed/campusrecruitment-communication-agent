import { useRef, useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import Card from "../Common/Card";
import VideoPreview from "./VideoPreview";
import FaceTrackingOverlay from "./FaceTrackingOverlay";
import RecordingControls from "./RecordingControls";
import TopicSpinner from "./TopicSpinner";
import { useMediaRecorder } from "../../hooks/useMediaRecorder";
import { useFaceTracking } from "../../hooks/useFaceTracking";
import { useAnalyzeSession, useUploadSession } from "../../hooks/useSessions";

export default function RecordingSession() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const recorder = useMediaRecorder();
  const uploadMutation = useUploadSession();
  const analyzeMutation = useAnalyzeSession();

  const paramTopic = searchParams.get("topic");
  const paramTrack = searchParams.get("track") || "jam";

  const [title, setTitle] = useState(paramTopic || "What habit would you like to develop next?");
  const [description, setDescription] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    if (paramTopic) {
      setTitle(paramTopic);
    }
  }, [paramTopic]);

  const faceState = useFaceTracking(
    videoRef,
    recorder.status === "recording" || recorder.status === "ready"
  );

  const isUploading = uploadMutation.isPending || analyzeMutation.isPending;

  async function handleUpload() {
    if (!recorder.videoBlob) return;
    setUploadError(null);
    try {
      const session = await uploadMutation.mutateAsync({
        title: title.trim() || "Practice Session",
        description: description.trim() || undefined,
        durationSeconds: recorder.elapsedMs / 1000,
        roundType: paramTrack,
        roundMetadata: {
          persona: localStorage.getItem("verbaliq_preset_persona") || "Bar Raiser",
          target_wpm: Number(localStorage.getItem("verbaliq_preset_wpm") || 140),
        },
        videoBlob: recorder.videoBlob,
      });
      await analyzeMutation.mutateAsync(session.id);
      recorder.reset();
      navigate(`/analysis/${session.id}`);
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail =
        axiosError?.response?.data?.detail ||
        axiosError?.message ||
        "Failed to upload and analyze session. Please try again.";
      setUploadError(String(detail));
    }
  }

  const handleRetake = async () => {
    recorder.reset();
    await recorder.init();
  };


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
            onReset={handleRetake}
            onUpload={handleUpload}
            uploading={isUploading}
          />
          {recorder.error ? (
            <p className="mt-4 text-sm text-rose-300">{recorder.error}</p>
          ) : null}
          {uploadError ? (
            <div className="mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-sm text-rose-300">
              {uploadError}
            </div>
          ) : null}
        </div>
      </Card>

      <Card>
        <motion.div
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          className="space-y-5"
        >
          <TopicSpinner
            topic={title}
            onTopicChange={setTitle}
            disabled={recorder.status === "recording" || isUploading}
          />

          <div className="space-y-1.5">
            <label className="block text-xs uppercase tracking-wide font-semibold text-outline font-label-caps">
              Session Notes / Talking Points (Optional)
            </label>
            <textarea
              className="w-full rounded-xl bg-surface-container border border-outline-variant/40 px-4 py-2.5 text-sm min-h-[85px] text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary transition-colors font-medium"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Key angles or ideas for your 60-second round..."
            />
          </div>

          {/* JAM Cardinal Rules Card */}
          <div className="rounded-xl p-4 bg-surface-container border border-outline-variant/40 space-y-2.5">
            <div className="text-xs font-bold text-secondary uppercase tracking-wider flex items-center gap-1.5 font-label-caps">
              <span className="material-symbols-outlined text-[18px] text-secondary">gavel</span>
              The 3 Cardinal Rules of JAM
            </div>
            <ul className="text-xs text-on-surface-variant space-y-2 font-medium">
              <li className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-error" />
                <span><strong className="text-on-surface">No Hesitation:</strong> No fillers (um, uh, like), stutters, or long pauses.</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-secondary" />
                <span><strong className="text-on-surface">No Repetition:</strong> Do not loop over the same words or phrases.</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-tertiary" />
                <span><strong className="text-on-surface">No Deviation:</strong> Stay on point with your topic for all 60 seconds.</span>
              </li>
            </ul>
          </div>
        </motion.div>
      </Card>
    </div>
  );
}
