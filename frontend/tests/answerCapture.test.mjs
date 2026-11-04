/**
 * Deterministic tests for the capture window around one interview question.
 *
 * No browser, no microphone, no network: a `MediaRecorder` is an object with `state`, `stop()` and the
 * two callbacks this module attaches, so the ordering that the studio depends on — the final chunk
 * arriving after `stop()` and `onstop` after that — can be reproduced exactly and asserted.
 *
 * Run:  node --test frontend/tests/answerCapture.test.mjs   (from the repository root)
 */
import test from "node:test";
import assert from "node:assert/strict";

import { AnswerCapture, startTake } from "../src/lib/answerCapture.ts";

/**
 * A recorder that delivers its data the way the browser does: `stop()` queues the last
 * `ondataavailable`, and `onstop` runs after it.
 */
class FakeRecorder {
  constructor() {
    this.state = "inactive";
    this.ondataavailable = null;
    this.onstop = null;
    this.stopCalls = 0;
    this.flushMode = "async";
  }

  start() {
    this.state = "recording";
  }

  /** One chunk of spoken audio, as the engine would deliver it. */
  speak(text) {
    if (this.state !== "recording") throw new Error("recording while stopped");
    this.ondataavailable?.({ data: new Blob([text]) });
  }

  stop() {
    this.stopCalls += 1;
    this.state = "inactive";
    // The tail of the take: in the browser this arrives after stop() returned, which is precisely the
    // race a submit that did not wait for `onstop` used to lose.
    const tail = () => {
      this.ondataavailable?.({ data: new Blob(["|tail"]) });
      this.onstop?.();
    };
    if (this.flushMode === "sync") tail();
    else setImmediate(tail);
  }

  /** Deliver the tail synchronously, for tests that need the promise already settled. */
  stopNow() {
    this.state = "inactive";
    this.onstop?.();
  }
}

// ---------------------------------------------------------------------------
// The window: one question's callbacks cannot reach the next question
// ---------------------------------------------------------------------------

test("a recording cannot start once a submission has begun", () => {
  const capture = new AnswerCapture();
  const token = capture.beginRecording();
  assert.equal(token, capture.questionToken);

  capture.beginSubmit();
  assert.equal(capture.beginRecording(), null, "the microphone opened during a submit");
  assert.equal(capture.captureStatus, "submitting");
});

test("a late transcript callback from the submitted question cannot edit its answer", () => {
  const capture = new AnswerCapture();
  const spoken = capture.beginRecording();
  capture.endRecording();
  capture.beginSubmit();

  // The engine flushes a final result after stop() — the answer has already left.
  assert.equal(capture.accepts(spoken), false);
});

test("a callback from an earlier question cannot modify the next question", () => {
  const capture = new AnswerCapture();
  const first = capture.beginRecording();
  capture.endRecording();
  capture.beginSubmit();

  const second = capture.nextQuestion();
  assert.notEqual(second, first, "the next question reused the previous window");

  // The first question's callbacks are the ones that arrive late, after the UI moved on.
  assert.equal(capture.accepts(first), false);
  assert.equal(capture.isCurrent(first), false);
  assert.equal(capture.accepts(second), true);
});

test("an old window ending does not reset the state of the question on screen", () => {
  const capture = new AnswerCapture();
  const first = capture.beginRecording();
  capture.beginSubmit();
  const second = capture.nextQuestion();
  capture.beginRecording();

  // onend for the first question arrives while the second is being recorded.
  assert.equal(capture.isCurrent(first), false);
  assert.equal(capture.isCurrent(second), true);
  assert.equal(capture.captureStatus, "recording", "the stale onend closed the live window");
});

test("an unknown or missing token is never current", () => {
  const capture = new AnswerCapture();
  assert.equal(capture.isCurrent(null), false);
  assert.equal(capture.isCurrent(undefined), false);
  assert.equal(capture.accepts(987654), false);
});

test("a failed submission re-opens the same question for retry", () => {
  const capture = new AnswerCapture();
  const token = capture.beginRecording();
  capture.endRecording();
  capture.beginSubmit();
  capture.abortSubmit();

  assert.equal(capture.captureStatus, "open");
  assert.equal(capture.questionToken, token, "the retry moved to a different question");
  assert.equal(capture.beginRecording(), token);
  assert.equal(capture.accepts(token), true);
});

test("closing a window that was already submitted leaves the submit lock in place", () => {
  const capture = new AnswerCapture();
  capture.beginRecording();
  capture.beginSubmit();
  capture.endRecording(); // the recognizer's onend lands mid-submit and must not unlock the controls

  assert.equal(capture.captureStatus, "submitting");
  assert.equal(capture.beginRecording(), null);
});

// ---------------------------------------------------------------------------
// The take: its audio is complete before the answer is finalized
// ---------------------------------------------------------------------------

test("stopAndCollect resolves after the final chunk, not at stop()", async () => {
  const recorder = new FakeRecorder();
  recorder.start();

  // Handlers attach before anything is spoken, exactly as the studio does it: the take owns the
  // recorder for its whole life, so no chunk can arrive while nobody is listening.
  const take = startTake(recorder, 1);
  recorder.speak("answer");

  const blob = await take.stopAndCollect();

  assert.equal(recorder.stopCalls, 1, "the recorder was never stopped");
  assert.ok(blob, "the take produced no audio even though chunks arrived");
  assert.equal(await blob.text(), "answer|tail", "the tail of the recording was lost");
});

test("stopAndCollect releases the microphone once, however often it is called", async () => {
  const recorder = new FakeRecorder();
  recorder.start();

  let releases = 0;
  const take = startTake(recorder, 1, () => {
    releases += 1;
  });
  recorder.speak("answer");

  const first = await take.stopAndCollect();
  const second = await take.stopAndCollect();

  assert.ok(first, "an empty take was handed back where audio was captured");
  assert.equal(second, first, "a second call rebuilt the audio instead of reusing it");
  assert.equal(releases, 1, "the tracks were released more than once");
  assert.equal(take.stopped, true);
});

test("two takes never share a buffer", async () => {
  const firstRecorder = new FakeRecorder();
  firstRecorder.start();
  const first = startTake(firstRecorder, 1);
  firstRecorder.speak("question-one");
  firstRecorder.stopNow();
  const firstBlob = await first.stopAndCollect();

  const secondRecorder = new FakeRecorder();
  secondRecorder.start();
  const second = startTake(secondRecorder, 2);
  secondRecorder.speak("question-two");
  secondRecorder.stopNow();
  const secondBlob = await second.stopAndCollect();

  assert.equal(await firstBlob.text(), "question-one");
  assert.equal(await secondBlob.text(), "question-two", "the next question inherited the previous audio");
});

test("a late chunk from a stopped recorder cannot enter the next question's take", () => {
  const firstRecorder = new FakeRecorder();
  firstRecorder.start();
  const first = startTake(firstRecorder, 1);
  firstRecorder.stopNow();

  const secondRecorder = new FakeRecorder();
  secondRecorder.start();
  const second = startTake(secondRecorder, 2);
  secondRecorder.speak("clean");

  // The orphaned first recorder delivers one more chunk after its own onstop, into its own buffer.
  firstRecorder.ondataavailable?.({ data: new Blob(["late"]) });

  secondRecorder.stopNow();
  return second.stopAndCollect().then(async (blob) => {
    assert.equal(await blob.text(), "clean");
  });
});

test("a recorder that never started yields no audio and is not stopped", async () => {
  const recorder = new FakeRecorder();
  let released = false;
  const take = startTake(recorder, 1, () => {
    released = true;
  });

  const blob = await take.stopAndCollect();

  assert.equal(blob, null, "an empty take was handed to the upload");
  assert.equal(recorder.stopCalls, 0, "stop() was called on a recorder that never started");
  assert.equal(released, true, "the microphone was left open");
});

test("a take with no audio at all reports null rather than an empty clip", async () => {
  const recorder = new FakeRecorder();
  recorder.start();
  const take = startTake(recorder, 1);
  recorder.stopNow(); // stopped before a single byte was captured

  assert.equal(await take.stopAndCollect(), null);
});

test("a take carries the token of the question that opened it", () => {
  const recorder = new FakeRecorder();
  const capture = new AnswerCapture();
  const token = capture.beginRecording();
  const take = startTake(recorder, token);
  assert.equal(take.token, token);
  assert.equal(capture.accepts(take.token), true);

  capture.beginSubmit();
  assert.equal(capture.accepts(take.token), false, "a finished take landed on a frozen question");
});
