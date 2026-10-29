import { useEffect, useRef, useState } from "react";

export interface LiveEmotionState {
  confidence: number;
  nervousness: number;
  composure: number;
  delivery_style?: string;
}

export interface CoachNudge {
  tier: 1 | 2;
  message: string;
}

export interface LiveStreamContext {
  category?: string;
  question?: string;
  partialTranscript?: string;
}

interface UseLiveEmotionStreamResult {
  liveEmotion: LiveEmotionState | null;
  isConnected: boolean;
  nudge: CoachNudge | null;
}

function resolveWsBase(): string {
  const custom =
    typeof localStorage !== "undefined"
      ? localStorage.getItem("speakflow_api_url")
      : null;
  const api =
    custom ||
    (import.meta.env.VITE_API_URL as string | undefined) ||
    "http://localhost:8000";

  try {
    const url = new URL(api, window.location.origin);
    const protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${url.host}`;
  } catch {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }
}

export function useLiveEmotionStream(
  sessionId: number | null,
  isRecording: boolean,
  context?: LiveStreamContext
): UseLiveEmotionStreamResult {
  const [liveEmotion, setLiveEmotion] = useState<LiveEmotionState | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [nudge, setNudge] = useState<CoachNudge | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cancelledRef = useRef(false);
  const contextRef = useRef<LiveStreamContext | undefined>(context);

  useEffect(() => {
    contextRef.current = context;
  }, [context]);

  useEffect(() => {
    if (!isRecording) setNudge(null);
  }, [isRecording]);

  useEffect(() => {
    if (!sessionId || !isRecording) {
      return;
    }

    cancelledRef.current = false;
    let ws: WebSocket | null = null;
    let recorder: MediaRecorder | null = null;
    let stream: MediaStream | null = null;

    const cleanup = () => {
      cancelledRef.current = true;

      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          // ignore recorder shutdown errors
        }
      }
      recorderRef.current = null;

      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      streamRef.current = null;

      if (
        ws &&
        (ws.readyState === WebSocket.OPEN ||
          ws.readyState === WebSocket.CONNECTING)
      ) {
        try {
          ws.close();
        } catch {
          // ignore socket shutdown errors
        }
      }
      wsRef.current = null;
      setIsConnected(false);
    };

    const start = async () => {
      try {
        ws = new WebSocket(
          `${resolveWsBase()}/ws/session/${sessionId}/emotion`
        );
        ws.binaryType = "arraybuffer";
        wsRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          if (contextRef.current) {
            try {
              ws?.send(
                JSON.stringify({
                  type: "context",
                  ...contextRef.current,
                })
              );
            } catch {
              // ignore context send errors
            }
          }
        };
        ws.onclose = () => setIsConnected(false);
        ws.onerror = () => setIsConnected(false);
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data as string);
            if (data?.type === "clear_nudge") {
              setNudge(null);
              return;
            }
            if (
              data?.type === "coach_nudge" &&
              typeof data.message === "string"
            ) {
              setNudge({
                tier: data.tier === 2 ? 2 : 1,
                message: data.message,
              });
              return;
            }
            if (typeof data?.confidence === "number") {
              setLiveEmotion({
                confidence: data.confidence,
                nervousness:
                  typeof data.nervousness === "number" ? data.nervousness : 0,
                composure:
                  typeof data.composure === "number" ? data.composure : 0,
                delivery_style: data.delivery_style,
              });
            }
          } catch {
            // ignore malformed frames
          }
        };

        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelledRef.current) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;

        const mimeCandidates = ["audio/webm;codecs=opus", "audio/webm"];
        const mimeType =
          mimeCandidates.find((candidate) =>
            MediaRecorder.isTypeSupported(candidate)
          ) || "";

        recorder = new MediaRecorder(
          stream,
          mimeType ? { mimeType } : undefined
        );
        recorderRef.current = recorder;

        recorder.ondataavailable = (event) => {
          if (!event.data || event.data.size === 0) return;
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(event.data);
          }
        };

        recorder.start(1500);
      } catch {
        setIsConnected(false);
      }
    };

    start();

    return cleanup;
  }, [sessionId, isRecording]);

  const category = context?.category;
  const question = context?.question;
  const partialTranscript = context?.partialTranscript;

  useEffect(() => {
    if (!category && !question && !partialTranscript) return;
    const ws = wsRef.current;
    if (!isRecording || !ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(
        JSON.stringify({
          type: "context",
          category,
          question,
          partialTranscript,
        })
      );
    } catch {
      // ignore context send errors
    }
  }, [category, question, partialTranscript, isRecording]);

  useEffect(() => {
    return () => {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try {
          recorderRef.current.stop();
        } catch {
          // ignore
        }
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  return { liveEmotion, isConnected, nudge };
}
