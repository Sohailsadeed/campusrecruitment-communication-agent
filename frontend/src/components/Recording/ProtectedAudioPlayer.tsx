/*
 * AUTH-E playback for a protected recording.
 *
 * The clip is fetched through apiClient so the bearer token travels with it, and played from an
 * object URL — a media element cannot authenticate, and pointing one at /api/... would have asked
 * the browser to fetch an owned recording with no credentials at all.
 *
 * The attempt/status pair lives in a per-instance store rather than in React state, and is read
 * with useSyncExternalStore. That is deliberate: the release of the object URL happens inside a
 * cleanup, and a claim about that resource has to be gone in the same synchronous step. Kept in
 * state, the invalidation would ride the ambient update lane of the commit phase, which under
 * StrictMode's development replay is DefaultLane and can be painted over after the resource is
 * already revoked. Store reads are synchronous, so no render can observe that ordering.
 */
import { useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { apiClient } from "../../api/client";
import {
  attemptCleanup,
  createClipStore,
  describeAudioError,
  fetchProtectedAudio,
  isStaleResponse,
  playbackReleaseSteps,
  resolveClipStatus,
  runSequential,
  type NamedStep,
} from "../../api/audioBlob";

type Props = { audioUrl?: string; className?: string };
type PendingRecord = { gen: number; ctrl: AbortController };
type OwnedRecord = { gen: number; url: string; el: HTMLAudioElement; objectUrl: string };

function msgOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Failures are surfaced, never swallowed, and never thrown back into React's commit phase. */
function reportCleanupFailures(failures: string[]): void {
  if (failures.length > 0) {
    console.error("ProtectedAudioPlayer: teardown steps failed", failures);
  }
}

export function ProtectedAudioPlayer({ audioUrl, className }: Props) {
  const url = audioUrl ?? "";
  const [store] = useState(createClipStore);
  const elRef = useRef<HTMLAudioElement | null>(null);
  const pendingRef = useRef<PendingRecord | null>(null);
  const ownedRef = useRef<OwnedRecord | null>(null);

  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const view = resolveClipStatus(snapshot.status, snapshot.attempt, url);

  useLayoutEffect(() => {
    const gen = store.beginAttempt(url); // published synchronously, before this effect returns
    if (!url) {
      return () => {
        release(gen);
      };
    }

    const ctrl = new AbortController();
    pendingRef.current = { gen, ctrl }; // registered before dispatch, so cleanup can always abort
    try {
      fetchProtectedAudio(apiClient, url, ctrl.signal)
        .then((blob) => {
          releasePending(gen, ctrl); // ownership of the request ends the moment it settles
          install(gen, url, blob, ctrl);
        })
        .catch((err) => {
          releasePending(gen, ctrl);
          if (isStaleResponse(gen, store.currentGen(), ctrl.signal.aborted)) {
            noteCancelled(gen, err); // our own abort is not a playback failure
            return;
          }
          store.publishError(gen, url, describeAudioError(err)); // the store re-checks currency
        });
    } catch (err) {
      // A rejected destination throws before a single byte is requested: no token ever leaves.
      releasePending(gen, ctrl);
      store.publishError(gen, url, `request-refused: ${msgOf(err)}`);
    }

    return () => {
      release(gen); // clip change, unmount and the StrictMode replay all arrive here
    };
  }, [url]);

  /** One synchronous block: the claim is gone before the resource is released. */
  function release(gen: number) {
    store.retract(gen);
    const steps: NamedStep[] = [];
    const pending = pendingRef.current;
    if (pending && pending.gen === gen) {
      pendingRef.current = null;
      steps.push(["abort", () => pending.ctrl.abort()]);
    }
    const owned = ownedRef.current;
    if (owned && owned.gen === gen) {
      ownedRef.current = null;
      steps.push(...playbackReleaseSteps(owned));
    }
    reportCleanupFailures(attemptCleanup(steps));
  }

  function releasePending(gen: number, ctrl: AbortController) {
    const record = pendingRef.current;
    if (record && record.gen === gen && record.ctrl === ctrl) {
      pendingRef.current = null; // a late settle only ever clears its own request
    }
  }

  function install(gen: number, url: string, blob: Blob, ctrl: AbortController) {
    if (isStaleResponse(gen, store.currentGen(), ctrl.signal.aborted)) return; // before any resource exists
    const el = elRef.current;
    if (!el) {
      store.publishError(gen, url, "player-element-missing");
      return; // nothing was created, so there is nothing to release
    }
    let objectUrl: string;
    try {
      objectUrl = URL.createObjectURL(blob);
    } catch (err) {
      store.publishError(gen, url, `createObjectURL: ${msgOf(err)}`);
      return;
    }

    const record: OwnedRecord = { gen, url, el, objectUrl };
    ownedRef.current = record; // claim first: the revoking step is the step that owns it
    const outcome = runSequential([
      ["setAttribute", () => el.setAttribute("src", objectUrl)],
      ["publishReady", () => { if (!store.publishReady(gen, url)) throw new Error("ready-publication-rejected"); }],
    ]);
    if (outcome.ok && store.currentGen() === gen) return;

    const failures = attemptCleanup(playbackReleaseSteps(record));
    if (ownedRef.current === record) ownedRef.current = null;
    reportCleanupFailures(failures);
    store.publishError(
      gen,
      url,
      outcome.ok ? "generation-superseded-during-install" : `${outcome.step}: ${outcome.message}`
    );
  }

  function noteCancelled(gen: number, err: unknown) {
    console.info(`ProtectedAudioPlayer: request for generation ${gen} was cancelled: ${msgOf(err)}`);
  }

  // React never sets `src` here — the only writer of that attribute is install(), and the only
  // writer of the retraction is release(). Keeping the element mounted is what lets both do it.
  return (
    <>
      <audio
        ref={elRef}
        controls
        className={className}
        aria-busy={view?.phase !== "ready"}
        hidden={view?.phase !== "ready"}
      />
      {view?.phase === "loading" && (
        <span role="status" className="text-xs text-outline">
          Loading…
        </span>
      )}
      {view?.phase === "error" && (
        <span role="alert" className="text-xs text-error">
          Playback unavailable: {view.reason}
        </span>
      )}
    </>
  );
}
