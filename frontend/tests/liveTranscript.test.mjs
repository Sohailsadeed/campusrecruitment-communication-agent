/**
 * Deterministic tests for live speech-recognition aggregation, driven by synthetic events.
 *
 * No browser, no microphone, no network: a Web Speech `SpeechRecognitionEvent` is just
 * `{ resultIndex, results }`, and a result is just `{ isFinal, length, 0: { transcript } }`, so the
 * provider contract can be reproduced exactly and the aggregator asserted against it.
 *
 * Run:  node --test frontend/tests/liveTranscript.test.mjs   (from the repository root)
 */
import test from "node:test";
import assert from "node:assert/strict";

import { LiveTranscriptAggregator } from "../src/lib/liveTranscript.ts";

/** One recognition result holding a single hypothesis. */
function result(transcript, isFinal) {
  return { isFinal, length: 1, 0: { transcript } };
}

/**
 * A recognition event over the session's growing result list.
 *
 * `entries` is the whole list as the engine would see it at that moment — earlier segments already
 * finalized, the current one still interim — because `results` is cumulative across the session and
 * `resultIndex` merely says where this event starts touching it.
 */
function event(resultIndex, entries) {
  return { resultIndex, results: entries.map(([text, isFinal]) => result(text, isFinal)) };
}

/**
 * The handler this module replaces: every result in the event appended as if it were new content.
 * Kept here so the regression test can prove the fix discriminates, rather than asserting against a
 * duplication the test only describes.
 */
function legacyHandler(events) {
  let answer = "";
  for (const ev of events) {
    let transcript = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      transcript += ev.results[i][0].transcript;
    }
    answer = answer ? `${answer} ${transcript}` : transcript;
  }
  return answer;
}

/**
 * How a studio page turns commits into the answer text it submits, event by event.
 *
 * `steps` records what the page looked like after each event, so a test can point at the exact moment
 * an interim existed and assert that nothing was persisted at it.
 */
function pageContract(aggregator, events) {
  let answerText = "";
  const persisted = [];
  const steps = [];
  let commits = 0;
  for (const ev of events) {
    for (const segment of aggregator.handle(ev)) {
      commits += 1;
      answerText = answerText ? `${answerText} ${segment}` : segment;
      persisted.push(segment);
    }
    steps.push({ pending: aggregator.pending(), answerText, commits });
  }
  return { answerText, persisted, steps, commits, pending: aggregator.pending() };
}

const SPOKEN = "The things that I found hardest about that role was owning a missed deadline";

/** The observed failure: cumulative interim snapshots for one segment, then one final. */
function observedInterimLadder() {
  const words = SPOKEN.split(" ");
  const events = [];
  for (let n = 1; n <= words.length; n++) {
    events.push(event(0, [[words.slice(0, n).join(" "), false]]));
  }
  events.push(event(0, [[SPOKEN, true]]));
  return events;
}

test("case 1 - cumulative interim updates replace the pending segment", () => {
  const aggregator = new LiveTranscriptAggregator();
  const events = [
    event(0, [["The", false]]),
    event(0, [["The things", false]]),
    event(0, [["The things that", false]]),
    event(0, [["The things that I", false]]),
  ];

  for (const ev of events) {
    assert.deepEqual(aggregator.handle(ev), [], "an interim hypothesis must not commit anything");
  }
  assert.equal(aggregator.pending(), "The things that I");
  assert.equal(aggregator.finalized(), "");
  assert.deepEqual(aggregator.segments(), []);
});

test("case 2 - the final result replaces the interim it belongs to", () => {
  const aggregator = new LiveTranscriptAggregator();
  assert.deepEqual(aggregator.handle(event(0, [["The things that I found", false]])), []);
  const committed = aggregator.handle(event(0, [["The things that I found", true]]));

  assert.deepEqual(committed, ["The things that I found"]);
  assert.equal(aggregator.pending(), "", "the segment's interim state is cleared on finalization");
  assert.equal(aggregator.finalized(), "The things that I found");
  assert.deepEqual(aggregator.segments(), [{ index: 0, text: "The things that I found" }]);
});

test("case 3 - distinct finalized segments keep their order", () => {
  const aggregator = new LiveTranscriptAggregator();
  const commits = [];
  commits.push(...aggregator.handle(event(0, [["First answer point", true]])));
  commits.push(
    ...aggregator.handle(
      event(1, [
        ["First answer point", true],
        ["Second answer point", true],
      ]),
    ),
  );
  commits.push(
    ...aggregator.handle(
      event(2, [
        ["First answer point", true],
        ["Second answer point", true],
        ["Third answer point", false],
      ]),
    ),
  );

  assert.deepEqual(commits, ["First answer point", "Second answer point"]);
  assert.equal(aggregator.finalized(), "First answer point Second answer point");
  assert.equal(aggregator.pending(), "Third answer point");
});

test("case 4 - a duplicate final event commits once", () => {
  const aggregator = new LiveTranscriptAggregator();
  const twice = event(0, [["Ship it anyway", true]]);

  assert.deepEqual(aggregator.handle(twice), ["Ship it anyway"]);
  assert.deepEqual(aggregator.handle(twice), [], "the same final delivered again is not new content");
  assert.deepEqual(
    aggregator.handle(event(0, [["Ship it anyway", true]])),
    [],
    "a later event that re-reads a sealed index must not re-commit it",
  );
  assert.equal(aggregator.finalized(), "Ship it anyway");
  assert.equal(aggregator.segments().length, 1);
});

test("case 5 - out-of-order and stale events cannot corrupt the transcript", () => {
  const aggregator = new LiveTranscriptAggregator();

  // Segment 1 is delivered before segment 0 has produced any text at all: the event starts at index 1
  // and the earlier slot is simply not offered yet.
  assert.deepEqual(
    aggregator.handle(event(1, [["", true], ["second half", true]])),
    ["second half"],
  );
  assert.deepEqual(aggregator.handle(event(0, [["first half", true]])), ["first half"]);
  assert.equal(
    aggregator.finalized(),
    "first half second half",
    "the join follows result indices, not the order the events happened to arrive in",
  );

  // A stale snapshot for a sealed index cannot leave an interim behind.
  assert.deepEqual(aggregator.handle(event(0, [["first half", false]])), []);
  assert.equal(aggregator.pending(), "");
  assert.equal(aggregator.finalized(), "first half second half");
  assert.deepEqual(aggregator.segments(), [
    { index: 0, text: "first half" },
    { index: 1, text: "second half" },
  ]);
});

test("case 6 - a candidate repeating themselves out loud is not deduplicated", () => {
  const aggregator = new LiveTranscriptAggregator();
  const commits = [];
  commits.push(...aggregator.handle(event(0, [["I was responsible for the migration", true]])));
  commits.push(
    ...aggregator.handle(
      event(1, [
        ["I was responsible for the migration", true],
        ["I was responsible for the migration", true],
      ]),
    ),
  );
  commits.push(
    ...aggregator.handle(
      event(2, [
        ["I was responsible for the migration", true],
        ["I was responsible for the migration", true],
        ["Twice", false],
      ]),
    ),
  );

  assert.deepEqual(commits, [
    "I was responsible for the migration",
    "I was responsible for the migration",
  ]);
  assert.equal(
    aggregator.finalized(),
    "I was responsible for the migration I was responsible for the migration",
    "identical text at different indices is identical speech, not a duplicate event",
  );
});

test("case 7 - two streams aggregate independently", () => {
  const candidate = new LiveTranscriptAggregator();
  const coach = new LiveTranscriptAggregator();

  assert.deepEqual(candidate.handle(event(0, [["candidate spoke first", false]])), []);
  assert.deepEqual(coach.handle(event(0, [["coach spoke first", false]])), []);
  assert.deepEqual(candidate.handle(event(0, [["candidate spoke first", true]])), [
    "candidate spoke first",
  ]);
  assert.deepEqual(coach.handle(event(0, [["coach spoke first", true]])), ["coach spoke first"]);

  // An index shared between the two streams must not make either one drop a segment.
  assert.deepEqual(candidate.handle(event(1, [
    ["candidate spoke first", true],
    ["candidate spoke second", true],
  ])), ["candidate spoke second"]);
  assert.equal(candidate.finalized(), "candidate spoke first candidate spoke second");
  assert.equal(coach.finalized(), "coach spoke first", "one stream's growth is the other's business");
});

test("case 8 - an unfinished interim is cleared, not persisted, when the session ends", () => {
  const aggregator = new LiveTranscriptAggregator();
  aggregator.handle(event(0, [["a finished thought", true]]));
  aggregator.handle(event(1, [
    ["a finished thought", true],
    ["and a thought cut off mid", false],
  ]));
  assert.equal(aggregator.pending(), "and a thought cut off mid");

  aggregator.clearPending();
  assert.equal(aggregator.pending(), "");
  assert.equal(aggregator.finalized(), "a finished thought");

  // A fresh session restarts result indices; without the reset they would collide with sealed ones.
  aggregator.reset();
  assert.equal(aggregator.finalized(), "");
  assert.equal(aggregator.pending(), "");
  assert.deepEqual(
    aggregator.handle(event(0, [["next question next answer", true]])),
    ["next question next answer"],
    "indices are reused by the next recognition session",
  );

  const collided = new LiveTranscriptAggregator();
  collided.handle(event(0, [["kept", true]]));
  assert.deepEqual(
    collided.handle(event(0, [["dropped as duplicate without reset", true]])),
    [],
    "documents why a page has to reset() between starts",
  );
});

test("case 9 - only finalized text reaches the answer that is submitted", () => {
  const aggregator = new LiveTranscriptAggregator();
  const { answerText, persisted, steps, commits } = pageContract(aggregator, [
    event(0, [["The", false]]),
    event(0, [["The things that", false]]),
    event(0, [["The things that I found", true]]),
    event(1, [
      ["The things that I found", true],
      ["the quality of the handover", false],
    ]),
    event(1, [
      ["The things that I found", true],
      ["the quality of the handover", true],
    ]),
  ]);

  assert.deepEqual(
    steps.map((step) => ({ pending: step.pending, answerText: step.answerText, commits: step.commits })),
    [
      { pending: "The", answerText: "", commits: 0 },
      { pending: "The things that", answerText: "", commits: 0 },
      { pending: "", answerText: "The things that I found", commits: 1 },
      { pending: "the quality of the handover", answerText: "The things that I found", commits: 1 },
      { pending: "", answerText: "The things that I found the quality of the handover", commits: 2 },
    ],
    "two commits for two segments; the three live interims persisted nothing",
  );
  assert.equal(commits, 2);
  assert.deepEqual(persisted, ["The things that I found", "the quality of the handover"]);
  assert.equal(answerText, aggregator.finalized());
  for (const step of steps) {
    if (step.pending && !aggregator.segments().some((s) => s.text === step.pending)) {
      assert.ok(
        !step.answerText.includes(step.pending),
        `live-only text ${JSON.stringify(step.pending)} must never be inside the submitted answer`,
      );
    }
  }
});

test("regression - the observed repeated-prefix pattern", () => {
  const events = observedInterimLadder();

  const before = legacyHandler(events);
  assert.ok(
    before.split(" ").length > SPOKEN.split(" ").length * 3,
    `the legacy handler must reproduce the duplication, got ${JSON.stringify(before)}`,
  );
  assert.ok(before.startsWith("The The things The things that"), before);

  const aggregator = new LiveTranscriptAggregator();
  const { answerText, commits } = pageContract(aggregator, events);

  assert.equal(commits, 1, "a cumulative ladder is one segment, so it is committed once");
  assert.equal(answerText, SPOKEN);
  assert.equal(answerText.split("The ").length - 1, 1, "the sentence is in the text exactly once");
  assert.equal(aggregator.pending(), "");
});

test("regression - two segments can be pending at once and finalize out of arrival order", () => {
  const aggregator = new LiveTranscriptAggregator();

  // One segment open.
  assert.deepEqual(aggregator.handle(event(0, [["the part I owned", false]])), []);
  assert.equal(aggregator.pending(), "the part I owned");

  // A second segment opens while the first is still interim: both must survive as their own slots.
  assert.deepEqual(
    aggregator.handle(event(0, [
      ["the part I owned and shipped", false],
      ["and the lesson", false],
    ])),
    [],
  );
  assert.equal(
    aggregator.pending(),
    "the part I owned and shipped and the lesson",
    "a second live segment must not wipe the first one's pending text",
  );

  // Only segment 0 moves; segment 1 keeps its own snapshot untouched.
  aggregator.handle(event(0, [
    ["the part I owned, then shipped", false],
    ["and the lesson", false],
  ]));
  assert.equal(aggregator.pending(), "the part I owned, then shipped and the lesson");

  // Segment 1 finalizes first.
  assert.deepEqual(aggregator.handle(event(1, [
    ["the part I owned, then shipped", false],
    ["and the lesson", true],
  ])), ["and the lesson"]);
  assert.equal(
    aggregator.pending(),
    "the part I owned, then shipped",
    "finalizing one segment leaves the other still pending",
  );

  // Segment 0 finalizes afterwards, at a lower result index.
  assert.deepEqual(aggregator.handle(event(0, [
    ["the part I owned, then shipped", true],
    ["and the lesson", true],
  ])), ["the part I owned, then shipped"]);
  assert.equal(aggregator.pending(), "");

  assert.equal(
    aggregator.finalized(),
    "the part I owned, then shipped and the lesson",
    "the canonical transcript follows result indices, not arrival order",
  );
  assert.deepEqual(aggregator.segments(), [
    { index: 0, text: "the part I owned, then shipped" },
    { index: 1, text: "and the lesson" },
  ]);

  // Delivering the whole ladder again commits nothing new.
  assert.deepEqual(aggregator.handle(event(0, [
    ["the part I owned, then shipped", true],
    ["and the lesson", true],
  ])), []);
  assert.equal(aggregator.segments().length, 2, "each segment is committed exactly once");
});

test("edge - whitespace-only and empty results are not content", () => {
  const aggregator = new LiveTranscriptAggregator();
  assert.deepEqual(aggregator.handle(event(0, [["   ", true]])), [], "an empty final is not a segment");
  assert.deepEqual(aggregator.handle(event(1, [["", true], ["  real   words  ", false]])), []);
  assert.equal(aggregator.pending(), "real words", "runs of whitespace collapse to single spaces");
  assert.deepEqual(aggregator.handle(event(1, [["", true], ["real words", true]])), ["real words"]);
  assert.equal(aggregator.finalized(), "real words");
  assert.deepEqual(aggregator.segments(), [{ index: 1, text: "real words" }]);
});

test("edge - a malformed event is handled without inventing text", () => {
  const aggregator = new LiveTranscriptAggregator();
  assert.deepEqual(aggregator.handle({ resultIndex: 0, results: undefined }), []);
  assert.deepEqual(aggregator.handle({ resultIndex: 0, results: [undefined] }), []);
  assert.deepEqual(aggregator.handle({ resultIndex: 5, results: [] }), []);
  assert.equal(aggregator.finalized(), "");
  assert.equal(aggregator.pending(), "");
});
