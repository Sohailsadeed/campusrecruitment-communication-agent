/*
 * AUTH-E: every protected clip fetch goes through here.
 *
 * Two reasons this file exists: a media element cannot send an Authorization header, so playback
 * needs an authenticated fetch plus a Blob/Object URL; and the string we fetch is read out of the
 * database, so it must be proven to be a SpeakFlow API path before the bearer token is attached to
 * it. Everything below is pure — no DOM and no React import — so the lifecycle logic is testable
 * outside a browser.
 */
import type { AxiosInstance } from "axios";

export type ClipPhase = "idle" | "loading" | "ready" | "error";
export type ClipStatus = { gen: number; url: string; phase: ClipPhase; reason: string | null };
export type Attempt = { url: string; gen: number } | null;
export type ClipSnapshot = { attempt: Attempt; status: ClipStatus };
export type ClipView = null | { phase: "loading" | "ready" | "error"; reason: string | null };
export type NamedStep = readonly [name: string, run: () => void];

/** Structural on purpose: the rollback path is exercised with a plain object in tests. */
export type PlaybackRecord = {
  el: { pause(): void; removeAttribute(name: string): void; load(): void };
  objectUrl: string;
};

export class AudioDestinationError extends Error {}

const ALLOWED_SCHEME = new Set(["http:", "https:"]);
const SENTINEL = "http://speakflow.invalid";
const API_URL_OVERRIDE_KEY = "speakflow_api_url";

type ApiBase = { defaults?: { baseURL?: string } };

function readStorageOverride(): string | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage.getItem(API_URL_OVERRIDE_KEY);
  } catch {
    return null; // a blocked storage area must not widen the allowed destination set
  }
}

function configuredOrigins(api: ApiBase): Set<string> {
  const bases = new Set<string>();
  const self = typeof window !== "undefined" ? window.location.origin : SENTINEL;
  // client.ts applies the storage override at request time, so a guard that looked only at
  // defaults.baseURL would wrongly reject a legitimately redirected deployment.
  for (const candidate of [api.defaults?.baseURL, readStorageOverride()]) {
    if (!candidate) continue;
    try {
      bases.add(new URL(candidate, self).origin);
    } catch {
      /* ignore an unusable base */
    }
  }
  if (bases.size === 0) bases.add(self);
  return bases;
}

/**
 * Returns a root-relative `/api/...` path, or throws before any request is dispatched.
 * A legacy absolute URL on a configured origin is re-homed onto its pathname, so the token's
 * destination is always the client's own origin — never whatever the stored row happens to say.
 */
export function toApiPath(raw: unknown, api: ApiBase): string {
  if (typeof raw !== "string" || !raw) throw new AudioDestinationError("Empty audio URL.");
  let candidate = raw;
  if (/^[a-z][a-z0-9+.-]*:/i.test(candidate)) {
    let parsed: URL;
    try {
      parsed = new URL(candidate);
    } catch {
      throw new AudioDestinationError("Malformed audio URL.");
    }
    if (!ALLOWED_SCHEME.has(parsed.protocol)) throw new AudioDestinationError("Unsupported audio URL scheme.");
    if (parsed.username || parsed.password) throw new AudioDestinationError("Malformed audio URL.");
    if (!configuredOrigins(api).has(parsed.origin)) throw new AudioDestinationError("External audio host blocked.");
    candidate = parsed.pathname + parsed.search;
  }
  if (!candidate.startsWith("/api/") || candidate.startsWith("//")) {
    throw new AudioDestinationError("Audio URL must be a SpeakFlow API path.");
  }
  const strict = new URL(candidate, SENTINEL); // WHATWG collapses "..", "%2e%2e" and backslashes
  if (strict.pathname !== candidate || strict.search !== "" || strict.hash !== "") {
    throw new AudioDestinationError("Malformed audio path.");
  }
  if (/[\s\u0000-\u0020\u007f]/.test(candidate)) throw new AudioDestinationError("Malformed audio path.");
  return candidate;
}

/** Resolves to the response body only; minting the object URL stays with the player so a stale
 *  settle can be rejected before any resource exists. */
export async function fetchProtectedAudio(api: AxiosInstance, url: string, signal: AbortSignal): Promise<Blob> {
  const path = toApiPath(url, api);
  const response = await api.get<Blob>(path, { responseType: "blob", signal, timeout: 300_000 });
  const blob = response?.data;
  if (!(blob instanceof Blob)) throw new AudioDestinationError("Unexpected audio response.");
  if (blob.size === 0) throw new Error("The recording is empty.");
  return blob;
}

/** User-facing copy for a playback failure. Synchronous: the response body is a Blob and the
 *  backend's denial copy is uniform, so reading the body would add nothing worth awaiting. */
export function describeAudioError(err: unknown): string {
  if (err instanceof AudioDestinationError) return "This recording cannot be played from here.";
  const status = (err as { response?: { status?: number } } | null)?.response?.status;
  if (status === 401) return "Your session has expired. Sign in again to play this recording.";
  if (status === 403 || status === 404) return "This recording is not available.";
  if (err instanceof Error && err.message) return err.message;
  return "This recording could not be loaded.";
}

/* ---- identity resolution: snapshot and props only, never a ref ---- */

export function resolveClipStatus(status: ClipStatus, attempt: Attempt, audioUrl: string): ClipView {
  if (!audioUrl) return null;
  if (!attempt || attempt.url !== audioUrl) return { phase: "loading", reason: null };
  if (status.gen !== attempt.gen || status.url !== attempt.url) return { phase: "loading", reason: null };
  return status.phase === "idle"
    ? { phase: "loading", reason: null }
    : { phase: status.phase, reason: status.reason };
}

export function isStaleResponse(settledGen: number, currentGen: number, aborted: boolean): boolean {
  return settledGen !== currentGen || aborted;
}

/* ---- rollback: every step attempted, in order; installation: sequential and fail-fast ---- */

export function playbackReleaseSteps(
  rec: PlaybackRecord,
  revoke: (objectUrl: string) => void = (objectUrl) => URL.revokeObjectURL(objectUrl)
): NamedStep[] {
  return [
    ["pause", () => rec.el.pause()],
    ["removeAttribute", () => rec.el.removeAttribute("src")],
    ["load", () => rec.el.load()],
    ["revokeObjectURL", () => revoke(rec.objectUrl)],
  ];
}

export function attemptCleanup(steps: ReadonlyArray<NamedStep>): string[] {
  const failures: string[] = [];
  for (const [name, run] of steps) {
    try {
      run();
    } catch (err) {
      failures.push(`${name}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  return failures; // never throws: a teardown failure is reported, not swallowed
}

export function runSequential(
  steps: ReadonlyArray<NamedStep>
): { ok: true } | { ok: false; step: string; message: string } {
  for (const [name, run] of steps) {
    try {
      run();
    } catch (err) {
      return { ok: false, step: name, message: err instanceof Error ? err.message : String(err) };
    }
  }
  return { ok: true };
}

/* ---- the clip store: one atomic snapshot per write, owner-guarded mutation ---- */

const IDLE_STATUS: ClipStatus = { gen: 0, url: "", phase: "idle", reason: null };
const EMPTY_SNAPSHOT: ClipSnapshot = { attempt: null, status: IDLE_STATUS };

export type ClipStore = {
  getSnapshot(): ClipSnapshot;
  subscribe(onChange: () => void): () => void;
  currentGen(): number;
  beginAttempt(url: string): number;
  retract(gen: number): boolean;
  publishReady(gen: number, url: string): boolean;
  publishError(gen: number, url: string, reason: string): boolean;
};

export function createClipStore(): ClipStore {
  let snap = EMPTY_SNAPSHOT;
  let gen = 0;
  const listeners = new Set<() => void>();

  const write = (next: ClipSnapshot) => {
    snap = next;
    for (const listener of Array.from(listeners)) listener();
  };
  const mine = (attempt: Attempt, target: number) => attempt !== null && attempt.gen === target;

  function publish(g: number, url: string, phase: "ready" | "error", reason: string | null): boolean {
    const attempt = snap.attempt;
    // A claim about an empty clip is meaningless, so an empty attempt is never publishable.
    if (!url || attempt === null || attempt.gen !== g || attempt.url !== url) return false;
    write({ attempt, status: { gen: g, url, phase, reason } });
    return true;
  }

  return {
    getSnapshot: () => snap,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    currentGen: () => gen,

    beginAttempt: (url) => {
      gen += 1;
      write({ attempt: { url, gen }, status: { gen, url, phase: "idle", reason: null } });
      return gen;
    },

    retract: (target) => {
      if (!mine(snap.attempt, target)) return false; // a stale run cannot clear a newer attempt
      gen += 1; // invalidation: any late settle for this generation becomes stale
      write({ attempt: null, status: IDLE_STATUS });
      return true;
    },

    publishReady: (g, url) => publish(g, url, "ready", null),
    publishError: (g, url, reason) => publish(g, url, "error", reason),
  };
}
