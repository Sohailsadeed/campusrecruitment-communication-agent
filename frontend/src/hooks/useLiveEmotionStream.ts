import { useEffect, useRef, useState } from "react";

export interface LiveEmotionState {
  confidence: number;
  nervousness: number;
  composure: number;
  delivery_style?: string;
  pitch_mean_hz?: number;
  pitch_std_hz?: number;
  is_monotone?: boolean;
  vocal_tremor?: boolean;
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
  context?: LiveStreamContext,
  externalStream?: MediaStream | null
): UseLiveEmotionStreamResult {
  const [liveEmotion, setLiveEmotion] = useState<LiveEmotionState | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [nudge, setNudge] = useState<CoachNudge | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ownsStreamRef = useRef(false);
  const cancelledRef = useRef(false);
  const contextRef = useRef<LiveStreamContext | undefined>(context);

  useEffect(() => {
    contextRef.current = context;
  }, [context]);

  useEffect(() => {
    if (!isRecording) setNudge(null);
  }, [isRecording]);

  useEffect(() => {
    if (sessionId === null || !isRecording) {
      return;
    }

    cancelledRef.current = false;
    let ws: WebSocket | null = null;
    let audioCtx: AudioContext | null = null;
    let source: MediaStreamAudioSourceNode | null = null;
    let workletNode: AudioWorkletNode | null = null;
    let stream: MediaStream | null = null;
    let ownsStream = false;

    const cleanup = () => {
      cancelledRef.current = true;

      if (workletNode) {
        workletNode.port.onmessage = null;
        try {
          workletNode.disconnect();
        } catch {
          // ignore worklet shutdown errors
        }
      }
      workletNodeRef.current = null;

      if (source) {
        try {
          source.disconnect();
        } catch {
          // ignore source shutdown errors
        }
      }
      sourceNodeRef.current = null;

      if (audioCtx) {
        void audioCtx.close().catch(() => {
          // ignore audio context shutdown errors
        });
      }
      audioContextRef.current = null;

      if (stream && ownsStream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      streamRef.current = null;
      ownsStreamRef.current = false;

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
                pitch_mean_hz:
                  typeof data.pitch_mean_hz === "number"
                    ? data.pitch_mean_hz
                    : 0,
                pitch_std_hz:
                  typeof data.pitch_std_hz === "number"
                    ? data.pitch_std_hz
                    : 0,
                is_monotone: Boolean(data.is_monotone),
                vocal_tremor: Boolean(data.vocal_tremor),
              });
            }
          } catch {
            // ignore malformed frames
          }
        };

        if (externalStream && externalStream.getAudioTracks().length > 0) {
          stream = new MediaStream(externalStream.getAudioTracks());
        } else {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          ownsStream = true;
          ownsStreamRef.current = true;
        }
        if (cancelledRef.current) {
          if (ownsStream) {
            stream.getTracks().forEach((track) => track.stop());
          }
          return;
        }
        streamRef.current = stream;

        const AudioContextCtor =
          window.AudioContext ||
          (
            window as typeof window & {
              webkitAudioContext?: typeof AudioContext;
            }
          ).webkitAudioContext;
        if (!AudioContextCtor) {
          throw new Error("AudioContext is not supported");
        }

        audioCtx = new AudioContextCtor();
        audioContextRef.current = audioCtx;
        await audioCtx.audioWorklet.addModule(
          `${import.meta.env.BASE_URL}audio-processor.js`
        );
        if (cancelledRef.current) return;
        if (audioCtx.state === "suspended") {
          await audioCtx.resume();
        }
        if (cancelledRef.current) return;

        source = audioCtx.createMediaStreamSource(stream);
        sourceNodeRef.current = source;
        workletNode = new AudioWorkletNode(audioCtx, "pcm-worklet-processor");
        workletNodeRef.current = workletNode;
        workletNode.port.onmessage = (event) => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(event.data);
          }
        };
        source.connect(workletNode);
        workletNode.connect(audioCtx.destination);
      } catch {
        if (ownsStream && stream) {
          stream.getTracks().forEach((track) => track.stop());
        }
        if (audioCtx) {
          void audioCtx.close().catch(() => {
            // ignore audio context shutdown errors
          });
        }
        if (ws) {
          try {
            ws.close();
          } catch {
            // ignore socket shutdown errors
          }
        }
        wsRef.current = null;
        setIsConnected(false);
      }
    };

    start();

    return cleanup;
  }, [sessionId, isRecording, externalStream]);

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
      if (workletNodeRef.current) {
        workletNodeRef.current.port.onmessage = null;
        try {
          workletNodeRef.current.disconnect();
        } catch {
          // ignore
        }
      }
      if (sourceNodeRef.current) {
        try {
          sourceNodeRef.current.disconnect();
        } catch {
          // ignore
        }
      }
      if (audioContextRef.current) {
        void audioContextRef.current.close().catch(() => {
          // ignore
        });
      }
      if (streamRef.current && ownsStreamRef.current) {
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
