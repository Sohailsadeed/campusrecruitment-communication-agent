import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ConnectionState, Room, RoomEvent, Track } from "livekit-client";
import { describeTokenError, fetchHrRoomAccess } from "../../api/livekit";

/**
 * The LiveKit V1 connection surface for one HR session: connect, publish the microphone, mute,
 * see the state, and leave cleanly.
 *
 * Deliberately narrow — this is the room, not the interview. The token comes from the backend for
 * the session id in the URL and is held in a local for exactly one connect call: never
 * localStorage, never console, never a query string. Everything the panel reports (room, identity,
 * expiry, whether the server has started receiving our audio) came back from the SFU, so what is
 * on screen is evidence, not an intention.
 */

type Phase =
  | "idle"
  | "requesting"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "failed";

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Not connected",
  requesting: "Asking the server for access…",
  connecting: "Connecting to the room…",
  connected: "Connected",
  reconnecting: "Reconnecting…",
  disconnected: "Disconnected",
  failed: "Connection failed",
};

const PHASE_TONE: Record<Phase, string> = {
  idle: "bg-surface-container text-on-surface-variant",
  requesting: "bg-surface-container text-secondary",
  connecting: "bg-surface-container text-secondary",
  connected: "bg-tertiary-container text-on-tertiary-container",
  reconnecting: "bg-secondary-container text-on-secondary-container",
  disconnected: "bg-surface-container text-on-surface-variant",
  failed: "bg-red-500/20 text-red-200",
};

/** The agent's own words, mapped for display. Anything unrecognised is shown as it arrived. */
const AGENT_STATE_LABEL: Record<string, string> = {
  connected: "Coach agent is in the room",
  listening: "Coach agent is listening for you",
  processing: "Coach agent is working out a reply",
  speaking: "Coach agent is speaking",
  completed: "Interview complete — your report is ready",
  asr_error: "Coach agent could not transcribe that round",
  closed: "Coach agent left the room",
};

/** Maps the browser's own permission failure onto something a candidate can act on. */
function describeMicrophoneError(error: unknown): string {
  const name = (error as { name?: string })?.name ?? "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone access was blocked. Allow it in the browser's address bar, then connect again.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No microphone was found. Connect one and try again.";
  }
  if (name === "NotReadableError") {
    return "Another application is using the microphone. Close it and try again.";
  }
  return "Could not open the microphone.";
}

export default function HRLiveRoom() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [micPublished, setMicPublished] = useState(false);
  const [micMuted, setMicMuted] = useState(false);
  const [serverReceiving, setServerReceiving] = useState(false);
  const [trackSid, setTrackSid] = useState<string | null>(null);
  const [roomName, setRoomName] = useState<string | null>(null);
  const [identity, setIdentity] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  // The agent's own reported state (connected / listening / processing / speaking), pushed as a
  // data message on the "agent_state" topic. Rendered only as what it is: what the agent said.
  const [agentState, setAgentState] = useState<string | null>(null);

  const roomRef = useRef<Room | null>(null);
  const disposedRef = useRef(false);
  // Rendered from state, not from the ref: a ref read during render would show a stale button
  // state, and these two controls must agree with the connection the user actually has.
  const [inRoom, setInRoom] = useState(false);

  // Client-side guard only: the backend re-derives everything from the authenticated caller, so a
  // hand-edited URL cannot reach another candidate's room — it just gets a 404.
  const parsedId = Number(sessionId);
  const sessionUsable = Number.isInteger(parsedId) && parsedId > 0;

  const teardown = useCallback((room: Room) => {
    room.removeAllListeners();
    // Unmounting mid-connect must not leave the capture device open behind the component.
    room.localParticipant.getTrackPublication(Track.Source.Microphone)?.audioTrack?.stop();
  }, []);

  useEffect(() => {
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
      const room = roomRef.current;
      roomRef.current = null;
      if (room !== null) {
        void room
          .disconnect()
          .catch(() => undefined)
          .finally(() => teardown(room));
      }
    };
  }, [teardown]);

  const connect = useCallback(async () => {
    if (!sessionUsable || roomRef.current !== null) return;
    setError(null);
    setPhase("requesting");

    let access;
    try {
      access = await fetchHrRoomAccess(parsedId);
    } catch (requestError) {
      if (!disposedRef.current) {
        setPhase("failed");
        setError(describeTokenError(requestError));
      }
      return;
    }
    if (disposedRef.current) return; // unmounted while the access request was in flight

    const room = new Room();
    roomRef.current = room;
    setInRoom(true);
    setRoomName(access.room_name);
    setIdentity(access.identity);
    setExpiresAt(access.expires_at);

    room.on(RoomEvent.ConnectionStateChanged, (state) => {
      if (disposedRef.current) return;
      if (state === ConnectionState.Connected) setPhase("connected");
      else if (state === ConnectionState.Reconnecting || state === ConnectionState.SignalReconnecting)
        setPhase("reconnecting");
      else if (state === ConnectionState.Disconnected) setPhase("disconnected");
      else setPhase("connecting");
    });
    room.on(RoomEvent.Reconnecting, () => !disposedRef.current && setPhase("reconnecting"));
    room.on(RoomEvent.Reconnected, () => !disposedRef.current && setPhase("connected"));
    room.on(RoomEvent.Disconnected, () => {
      if (disposedRef.current) return;
      setPhase("disconnected");
      setInRoom(false);
      setMicPublished(false);
      setMicMuted(false);
      setServerReceiving(false);
      setTrackSid(null);
      setAgentState(null);
      roomRef.current = null;
      teardown(room);
    });
    room.on(RoomEvent.LocalTrackPublished, (publication) => {
      if (disposedRef.current || publication.kind !== Track.Kind.Audio) return;
      setMicPublished(true);
      setMicMuted(publication.isMuted);
      setTrackSid(publication.trackSid);
    });
    room.on(RoomEvent.LocalTrackUnpublished, (publication) => {
      if (disposedRef.current || publication.kind !== Track.Kind.Audio) return;
      setMicPublished(false);
      setServerReceiving(false);
      setTrackSid(null);
    });
    // A bonus signal, not the proof of publishing: LiveKit only echoes a publisher's own track
    // back as a subscription when it chooses to, so absence means "no echo", not "no audio".
    room.on(RoomEvent.LocalTrackSubscribed, (publication) => {
      if (disposedRef.current || publication.kind !== Track.Kind.Audio) return;
      setServerReceiving(true);
    });
    room.on(RoomEvent.MediaDevicesError, (deviceError) => {
      if (!disposedRef.current) setError(`Media device problem: ${deviceError.message}`);
    });
    room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
      if (disposedRef.current || topic !== "agent_state") return;
      try {
        const message = JSON.parse(new TextDecoder().decode(payload)) as {
          agent?: string;
          state?: string;
        };
        if (message.agent === "hr-voice" && typeof message.state === "string") {
          setAgentState(message.state);
        }
      } catch {
        // A state message that is not JSON says nothing about the round; ignore it, keep audio.
      }
    });

    setPhase("connecting");
    try {
      await room.connect(access.url, access.token);
    } catch (connectError) {
      const detail =
        connectError instanceof Error ? connectError.message : "the room refused the connection";
      setPhase("failed");
      setError(`Could not join the room: ${detail}`);
      roomRef.current = null;
      setInRoom(false);
      await room.disconnect().catch(() => undefined);
      teardown(room);
      return;
    }

    try {
      // Echo cancellation is stated rather than inherited from the SDK default: the coach answers
      // out loud and the candidate's microphone must not carry that voice back to the agent as an
      // interruption. Noise suppression stays on for now — the agent's speech gate is on level, and
      // a noisier lane would trip it.
      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
    } catch (micError) {
      // Connected, but no microphone: say so precisely rather than pretending the round can go
      // ahead, and leave the room open so the candidate can still see the state.
      setError(describeMicrophoneError(micError));
    }
  }, [parsedId, sessionUsable, teardown]);

  const disconnect = useCallback(async () => {
    const room = roomRef.current;
    roomRef.current = null;
    setInRoom(false);
    setMicPublished(false);
    setMicMuted(false);
    setServerReceiving(false);
    setTrackSid(null);
    if (room === null) {
      setPhase("idle");
      return;
    }
    await room.disconnect();
    teardown(room);
    setPhase("disconnected");
  }, [teardown]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (room === null) return;
    const next = !micMuted;
    const microphone = room.localParticipant.getTrackPublication(Track.Source.Microphone);
    if (microphone === undefined) return;
    await (next ? microphone.mute() : microphone.unmute());
    setMicMuted(next);
  }, [micMuted]);

  const busy = phase === "requesting" || phase === "connecting";

  return (
    <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-3xl mx-auto flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <Link to={`/hr/${sessionId ?? ""}`} className="text-xs text-on-surface-variant hover:text-on-surface">
          ← Back to this interview
        </Link>
        <h1 className="font-headline-md text-2xl text-on-surface">Live audio room</h1>
        <p className="text-sm text-on-surface-variant">
          Connects this browser's microphone to SpeakFlow's self-hosted LiveKit server for session{" "}
          <span className="text-on-surface">#{sessionId}</span>.
        </p>
      </header>

      <section className="flex items-center gap-3 rounded-2xl bg-surface-container p-4">
        <span className={`px-3 py-1 rounded-full text-xs font-medium ${PHASE_TONE[phase]}`}>
          {PHASE_LABEL[phase]}
        </span>
        {phase === "connected" && micPublished && (
          <span className="text-xs text-on-surface-variant">
            {serverReceiving
              ? "The server has your microphone and is relaying it back"
              : "The server has accepted your microphone track"}
          </span>
        )}
        {phase === "connected" && !micPublished && (
          <span className="text-xs text-on-surface-variant">
            In the room, but no microphone track has been published yet
          </span>
        )}
        {agentState !== null && (
          <span className="text-xs text-secondary" data-agent-state={agentState}>
            {AGENT_STATE_LABEL[agentState] ?? `Coach agent: ${agentState}`}
          </span>
        )}
        {agentState === "completed" && (
          <Link
            to={`/hr/report/${sessionId ?? ""}`}
            className="text-xs text-primary underline"
            data-report-link="hr"
          >
            Open the behavioral report for this session
          </Link>
        )}
      </section>

      {!sessionUsable && (
        <p className="text-sm text-red-200">
          This page needs a session id in the URL — start the interview and open the room from it.
        </p>
      )}

      {error && (
        <p role="alert" className="text-sm rounded-xl bg-red-500/10 px-4 py-3 text-red-200">
          {error}
        </p>
      )}

      <section className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void connect()}
          disabled={!sessionUsable || inRoom}
          className="px-5 py-2 rounded-full bg-primary text-on-primary font-medium disabled:opacity-40"
        >
          {busy ? "Connecting…" : "Connect"}
        </button>
        <button
          type="button"
          onClick={() => void disconnect()}
          disabled={!inRoom}
          className="px-5 py-2 rounded-full border border-outline/60 text-on-surface disabled:opacity-40"
        >
          Disconnect
        </button>
        <button
          type="button"
          onClick={() => void toggleMute()}
          disabled={!micPublished}
          className="px-5 py-2 rounded-full border border-outline/60 text-on-surface disabled:opacity-40"
        >
          {micMuted ? "Unmute microphone" : "Mute microphone"}
        </button>
      </section>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm rounded-2xl border border-outline/30 p-4">
        <dt className="text-on-surface-variant">Room</dt>
        <dd className="text-on-surface break-all">{roomName ?? "—"}</dd>
        <dt className="text-on-surface-variant">You are</dt>
        <dd className="text-on-surface">{identity ?? "—"}</dd>
        <dt className="text-on-surface-variant">Microphone</dt>
        <dd className="text-on-surface">
          {micPublished ? `${micMuted ? "muted" : "publishing"}${trackSid ? ` · ${trackSid}` : ""}` : "not published"}
        </dd>
        <dt className="text-on-surface-variant">Access expires</dt>
        <dd className="text-on-surface">
          {expiresAt ? new Date(expiresAt).toLocaleTimeString() : "—"}
        </dd>
      </dl>

      <p className="text-xs text-on-surface-variant">
        Access is issued for this session only and lasts minutes, not hours — reload the page to get
        a fresh one. No recording is stored at this step.
      </p>
    </div>
  );
}
