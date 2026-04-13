import { motion } from "framer-motion";
import { Eye, EyeOff } from "lucide-react";

interface FaceTrackingOverlayProps {
  faceDetected: boolean;
  centered: boolean;
}

export default function FaceTrackingOverlay({
  faceDetected,
  centered,
}: FaceTrackingOverlayProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="absolute top-4 left-4 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 border border-white/10 backdrop-blur-md"
    >
      {faceDetected ? (
        <Eye className="w-4 h-4 text-emerald-400" />
      ) : (
        <EyeOff className="w-4 h-4 text-rose-400" />
      )}
      <span className="text-xs text-slate-200">
        {faceDetected
          ? centered
            ? "Framed well"
            : "Center yourself"
          : "No face detected"}
      </span>
    </motion.div>
  );
}
