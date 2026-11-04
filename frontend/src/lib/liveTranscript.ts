/**
 * Aggregation for live browser speech recognition (the Web Speech API).
 *
 * The provider's event contract is the thing being modelled here, so it is worth stating exactly:
 *
 * - `event.results` is a list that grows for the life of one recognition session. Each entry is one
 *   spoken segment, and `event.resultIndex` is the position of the first entry that this event
 *   touches.
 * - While a segment is still being spoken, its entry is *not final* and its `transcript` is a
 *   **cumulative snapshot of that whole segment** — "The things that" replaces "The things", it does
 *   not follow it.
 * - When the segment is complete the same index flips to `isFinal`, carrying the finalized text for
 *   that one segment.
 *
 * So the two rules that keep a transcript honest are: an interim snapshot *replaces* the pending
 * segment, and a final *commits* that segment once. Appending every result — which is what a plain
 * `transcript += results[i][0].transcript` does — turns each growing snapshot into new content and
 * produces the repeated-prefix pattern this module exists to prevent.
 *
 * Nothing here compares texts to each other. Segments are identified by their result index, because
 * text equality would silently eat a candidate genuinely repeating a phrase.
 */

export interface RecognitionAlternative {
  readonly transcript: string;
}

export interface RecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  readonly 0: RecognitionAlternative;
}

export interface RecognitionResultList {
  readonly length: number;
  readonly [index: number]: RecognitionResult | undefined;
}

export interface RecognitionEvent {
  readonly resultIndex: number;
  readonly results: RecognitionResultList;
}

export interface CommittedSegment {
  readonly index: number;
  readonly text: string;
}

function normalise(value: string | undefined | null): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

export class LiveTranscriptAggregator {
  /** index -> finalized text. A Map is the dedupe: one commit per index, however many events arrive. */
  private readonly finals = new Map<number, string>();
  /** index -> the latest snapshot of that segment while it is still being spoken. */
  private readonly pendingByIndex = new Map<number, string>();

  /**
   * Fold one recognition event into the transcript.
   *
   * Returns only the segments that became final in this event, which is the sole output callers may
   * persist or evaluate; everything else stays in `pending()`.
   */
  handle(event: RecognitionEvent): string[] {
    const committed: string[] = [];
    const results = event.results;
    if (!results) return committed;
    for (let i = Math.max(0, event.resultIndex); i < results.length; i++) {
      const result = results[i];
      if (!result) continue;
      const text = normalise(result.length > 0 ? result[0]?.transcript : "");

      if (result.isFinal) {
        if (this.finals.has(i)) continue;          // duplicate final delivery — already counted
        this.pendingByIndex.delete(i);
        // An empty final is a segment boundary the engine announced without hearing anything.
        if (!text) continue;
        this.finals.set(i, text);
        committed.push(text);
        continue;
      }

      if (this.finals.has(i)) continue;            // stale snapshot for a segment already sealed
      if (!text) {
        this.pendingByIndex.delete(i);
        continue;
      }
      this.pendingByIndex.set(i, text);            // cumulative snapshot replaces, never appends
    }
    return committed;
  }

  /**
   * The in-flight hypotheses, for live display only — never part of `finalized()`.
   *
   * More than one segment can be open at a time, so each keeps its own slot in result-index order.
   */
  pending(): string {
    return [...this.pendingByIndex.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([, text]) => text)
      .join(" ");
  }

  /** Ordered join of the finalized segments — the transcript that may be submitted. */
  finalized(): string {
    return this.segments()
      .map((segment) => segment.text)
      .join(" ");
  }

  /** Finalized segments in result-index order, so an out-of-order delivery cannot scramble them. */
  segments(): CommittedSegment[] {
    return [...this.finals.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([index, text]) => ({ index, text }));
  }

  clearPending(): void {
    this.pendingByIndex.clear();
  }

  /**
   * Forget everything, because this recognition session is over. Result indices restart on the next
   * `start()`, so keeping the old ones would let a fresh segment collide with a sealed index and be
   * dropped as a duplicate.
   */
  reset(): void {
    this.finals.clear();
    this.clearPending();
  }
}
