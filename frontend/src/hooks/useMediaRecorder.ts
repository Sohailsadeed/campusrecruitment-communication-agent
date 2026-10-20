import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderStatus = "idle" | "ready" | "recording" | "stopped" | "error";

interface UseMediaRecorderResult {
  status: RecorderStatus;
  error: string | null;
  stream: MediaStream | null;
  videoBlob: Blob | null;
  videoUrl: string | null;
  elapsedMs: number;
  init: () => Promise<void>;
  start: () => void;
  stop: () => void;
  reset: () => void;
}

export function useMediaRecorder(): UseMediaRecorderResult {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [videoBlob, setVideoBlob] = useState<Blob | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<number | null>(null);

  const init = useCallback(async () => {
    try {
      setError(null);
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720 },
        audio: true,
      });
      setStream(mediaStream);
      setStatus("ready");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unable to access camera";
      setError(message);
      setStatus("error");
    }
  }, []);

  const start = useCallback(() => {
    if (!stream) return;
    chunksRef.current = [];
    const mimeCandidates = [
      "video/webm;codecs=vp9,opus",
      "video/webm;codecs=vp8,opus",
      "video/webm",
    ];
    const mimeType =
      mimeCandidates.find((m) => MediaRecorder.isTypeSupported(m)) || "";
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, {
        type: mimeType || "video/webm",
      });
      setVideoBlob(blob);
      setVideoUrl(URL.createObjectURL(blob));
      setStatus("stopped");
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      setStream(null);
    };
    recorderRef.current = recorder;
    recorder.start(250);
    startTimeRef.current = Date.now();
    setElapsedMs(0);
    setStatus("recording");
    timerRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startTimeRef.current);
    }, 200);
  }, [stream]);

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
  }, []);

  const reset = useCallback(() => {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
    }
    setStream(null);
    setVideoBlob(null);
    setVideoUrl(null);
    setElapsedMs(0);
    setStatus("idle");
  }, [stream, videoUrl]);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      if (stream) stream.getTracks().forEach((t) => t.stop());
      if (videoUrl) URL.revokeObjectURL(videoUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    status,
    error,
    stream,
    videoBlob,
    videoUrl,
    elapsedMs,
    init,
    start,
    stop,
    reset,
  };
}
