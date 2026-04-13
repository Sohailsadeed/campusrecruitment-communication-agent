import { useEffect, useRef, useState } from "react";

interface FaceTrackingState {
  faceDetected: boolean;
  centered: boolean;
}

/**
 * Lightweight face presence estimator.
 *
 * This hook samples frames from the provided video element and uses the
 * Shape Detection API (FaceDetector) when available. If not, it falls back
 * to a heuristic "face assumed present" signal so the UI remains functional.
 */
export function useFaceTracking(
  videoRef: React.RefObject<HTMLVideoElement>,
  active: boolean
): FaceTrackingState {
  const [state, setState] = useState<FaceTrackingState>({
    faceDetected: false,
    centered: false,
  });
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active || !videoRef.current) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const FaceDetectorCtor = (window as any).FaceDetector;
    const detector = FaceDetectorCtor ? new FaceDetectorCtor() : null;

    let disposed = false;

    const tick = async () => {
      if (disposed || !videoRef.current) return;
      const video = videoRef.current;
      if (video.readyState < 2) {
        rafRef.current = window.requestAnimationFrame(tick);
        return;
      }
      try {
        if (detector) {
          const faces = await detector.detect(video);
          const first = faces[0];
          if (first) {
            const cx = first.boundingBox.x + first.boundingBox.width / 2;
            const centered = Math.abs(cx - video.videoWidth / 2) < video.videoWidth * 0.2;
            setState({ faceDetected: true, centered });
          } else {
            setState({ faceDetected: false, centered: false });
          }
        } else {
          // Fallback: assume present when video is playing
          setState({ faceDetected: !video.paused, centered: true });
        }
      } catch {
        setState({ faceDetected: false, centered: false });
      }
      rafRef.current = window.requestAnimationFrame(tick);
    };

    rafRef.current = window.requestAnimationFrame(tick);
    return () => {
      disposed = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active, videoRef]);

  return state;
}
