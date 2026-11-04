/**
 * The capture window around one interview question.
 *
 * Both defects this guards are timing, not data:
 * - a recording that is still running when the candidate submits belongs to a `MediaRecorder` nobody
 *   stopped, so its chunks keep arriving into a buffer the next question then reuses;
 * - callbacks from an earlier question still fire — a transcript the engine flushes on `stop()`, an
 *   `onstop` that lands after the UI moved on — and write into the question now on screen.
 *
 * So every capture action carries the token of the question that started it. A token stops being
 * current when the next question opens, and the window closes early when a submit begins: an answer
 * that has already left cannot be edited by something recorded before it.
 */

export type CaptureStatus = "open" | "recording" | "submitting";

export class AnswerCapture {
  private token = 1;
  private status: CaptureStatus = "open";

  get questionToken(): number {
    return this.token;
  }

  get captureStatus(): CaptureStatus {
    return this.status;
  }

  /** A new question is on screen: a fresh window, and the controls work again. */
  nextQuestion(): number {
    this.token += 1;
    this.status = "open";
    return this.token;
  }

  /** Open the microphone for this question. Refused once a submit has begun. */
  beginRecording(): number | null {
    if (this.status === "submitting") return null;
    this.status = "recording";
    return this.token;
  }

  /** The recognizer and recorder finished their own shutdown, leaving the question answerable again. */
  endRecording(): void {
    if (this.status === "recording") this.status = "open";
  }

  /** Freeze this question: no new recording, and no callback may edit the answer that is leaving. */
  beginSubmit(): void {
    this.status = "submitting";
  }

  /** The submit did not land, so this same question is still the one on screen and can be retried. */
  abortSubmit(): void {
    if (this.status === "submitting") this.status = "open";
  }

  /** Whether `token` is the question currently on screen — stale windows never touch its state. */
  isCurrent(token: number | null | undefined): boolean {
    return token !== null && token !== undefined && token === this.token;
  }

  /** Whether a callback holding `token` may still write the answer text or attach a recording. */
  accepts(token: number | null | undefined): boolean {
    return this.status !== "submitting" && this.isCurrent(token);
  }
}

/** The part of `MediaRecorder` a take drives, so a fake can stand in for it under test. */
export interface TakeRecorder {
  readonly state: string;
  stop(): void;
  ondataavailable: ((event: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
}

export interface Take {
  readonly token: number;
  readonly stopped: boolean;
  /**
   * Stop the recorder and resolve once its final data has arrived.
   *
   * Resolving on `stop()` rather than in the same tick is the whole point: the last
   * `ondataavailable` is delivered after it, so a submit that did not wait would upload a recording
   * that is missing its tail — or, if it also skipped the stop, none at all.
   */
  stopAndCollect(): Promise<Blob | null>;
}

/**
 * Own one recording from the moment it starts.
 *
 * The chunks live here, one array per take, so no two questions can ever share a buffer. `release`
 * runs when the audio is complete — that is where the microphone tracks are let go.
 */
export function startTake(recorder: TakeRecorder, token: number, release?: () => void): Take {
  const chunks: Blob[] = [];
  let settled = false;
  let resolveDone: (blob: Blob | null) => void = () => {};
  const done = new Promise<Blob | null>((resolve) => {
    resolveDone = resolve;
  });

  const finish = () => {
    if (settled) return;
    settled = true;
    if (release) release();
    // No chunks is a recording that captured nothing: null keeps it out of the upload instead of
    // sending an empty body the server would still have to store and transcribe.
    resolveDone(chunks.length ? new Blob(chunks, { type: "audio/webm" }) : null);
  };

  recorder.ondataavailable = (event) => {
    if (event && event.data && event.data.size > 0) chunks.push(event.data);
  };
  recorder.onstop = finish;

  return {
    token,
    get stopped() {
      return settled;
    },
    stopAndCollect() {
      // A recorder that never started has no final data to wait for, and `stop()` on it would throw.
      if (!settled && recorder.state === "inactive") finish();
      else if (!settled) recorder.stop();
      return done;
    },
  };
}
