# SpeakFlow — WebSocket Contract & Real-Time Communication Audit

**Audit date:** 2026-10-31
**Mode:** READ-ONLY. No source file was modified, created or deleted.
**Tree audited:** working tree on branch `feature/hr-round` @ `326d75e` **with uncommitted modifications present** (see §9). Findings describe the *working tree*, not `HEAD`.

Method: every file below was read in full. Claims are tagged **[V]** verified by reading code, **[V-live]** verified by executing the code (TestClient probe), **[I]** inferred from code without direct proof, **[U]** unknown / not establishable from the repo.

---

## 1. Inventory — there is exactly one WebSocket

| # | Path | Handler | Router file | Mount | Auth | Status |
|---|---|---|---|---|---|---|
| 1 | `/ws/session/{session_id}/emotion` | `emotion_websocket` | [emotion_stream.py:54-55](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/emotion_stream.py#L54) | `app.include_router(emotion_stream.router)` — **no prefix** ([main.py:87](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/main.py#L87)) | **None** | Working **[V-live]** |

**[V]** Exhaustive grep of `backend/` for `.websocket(` / `WebSocket` returns only `emotion_stream.py`. There is no second socket, no STT socket, no video socket, no pub/sub socket, no socket.io.

**[V-live]** Confirmed against a live `TestClient`: connect → send JSON context frame → send `close` → clean shutdown, no exception.

**[V]** It does **not** appear in the OpenAPI document (FastAPI never documents WS routes), so `/docs` and `/openapi.json` are not a complete contract surface for this application. 60 REST operations + 1 undocumented WS.

### Consumers of this single socket

| Call site | `sessionId` arg | `isRecording` | `context` | `externalStream` | Nudge consumed? |
|---|---|---|---|---|---|
| [RecordingSession.tsx:23-28](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Recording/RecordingSession.tsx#L23) (JAM) | **`0` — literal** | `recorder.status === "recording"` | `undefined` | `recorder.stream` | No (`liveEmotion` only) |
| [HRStudio.tsx:60](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/pages/hr/HRStudio.tsx#L60) | real DB id | recording state | **omitted** | omitted | No |
| [TechnicalStudio.tsx:99](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/pages/technical/TechnicalStudio.tsx#L99) | real DB id | recording state | **omitted** | omitted | No |
| [GuesstimateStudio.tsx:103-107](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/pages/guesstimate/GuesstimateStudio.tsx#L103) | real DB id | recording state | `{category, question, partialTranscript}` | omitted | **Yes** (`nudge`) |

Only **one of four** modules uses the coaching half of the protocol, and the module that does uses a key the server cannot read (§4.2).

---

## 2. Connection lifecycle

**Server side** ([emotion_stream.py:55-101](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/emotion_stream.py#L55)):

1. `await websocket.accept()` is the first statement. **No credential of any kind is inspected** — no `Authorization` header, no `?token=`, no cookie, no session-ownership check. `session_id` is an unvalidated integer from the URL path.
2. Local state initialised: `elapsed = 0.0`, `pcm_window = deque(maxlen=32000)`, EMA seeds `smooth_confidence=65.0`, `smooth_nervousness=22.0`, `smooth_composure=80.0`, `ALPHA = 0.35`.
3. `await asyncio.to_thread(_load_guesstimate_context, session_id)` — opens its **own** DB session (`SessionLocal()`), loads `Session.round_type` and, if `"guesstimate"`, `case.category` / `case.question`. Sets `is_guesstimate`.
4. Enters `while True: message = await websocket.receive()`.
5. **No welcome / hello / capability frame is ever sent.** The client cannot learn whether the server accepted guesstimate context, what sample rate it expects, or whether Laya is armed. `ws.onopen` fires optimistically.

**Client side** ([useLiveEmotionStream.ts:141-163](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/hooks/useLiveEmotionStream.ts#L141)):

- URL built by `resolveWsBase()` (:31-49) from `localStorage["speakflow_api_url"]` → `VITE_API_URL` → `http://localhost:8000`, then `http→ws` / `https→wss`. `new WebSocket(`${base}/ws/session/${sessionId}/emotion`)`, `ws.binaryType = "arraybuffer"`.
- `onopen` sets `isConnected = true` and, if a `context` prop exists, sends the first `{"type":"context", ...context}` frame.
- The socket effect re-runs on `[sessionId, isRecording, externalStream]` (:280) — **it opens only while recording**, and closes when `isRecording` falls.

**Termination:** client `cleanup()` (:91-139) tears down worklet → source → AudioContext → mic tracks → `ws.close()`. Server exits its loop on `websocket.disconnect` **or** on the text frames `"close"`, `"stop"`, `"end"` (case-insensitive, :110). `finally` (:313-319) cancels an in-flight tier-2 task and calls `await websocket.close()` inside a bare `except Exception: pass`.

**[V] The server never sends any of those terminator strings**, and the client never sends them either — the `"close"|"stop"|"end"` branch is an unused inbound verb (reachable only by a non-browser client).

---

## 3. Binary audio format — the real contract

### Negotiation is by content sniffing, not declaration **[V]**

`is_pcm16_chunk(payload)` ([audio_pcm.py:14-19](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/services/audio_pcm.py#L14)) decides how to interpret every binary frame:

```python
if not audio_bytes or len(audio_bytes) % 2 != 0:  return False
if audio_bytes.startswith(_MAGIC):                 return False   # b"\x1aE\xdf\xa3", b"RIFF", b"OggS", b"fLaC", b"ID3"
return len(audio_bytes) % PCM16_CHUNK_BYTES == 0                   # 3200
```

There is no `Content-Type`-equivalent handshake, no subprotocol, no header frame. Classification is a heuristic on byte length and magic bytes.

### Agreed wire format **[V — both ends match]**

| Property | Producer (browser) | Consumer (server) | Match |
|---|---|---|---|
| Encoding | `Int16Array` → `ArrayBuffer` | `np.frombuffer(..., dtype="<i2")` | ✅ s16le |
| Sample rate | `targetRate = 16000` (`audio-processor.js:5`) | `PCM16_SAMPLE_RATE = 16000` (:9) | ✅ |
| Channels | mono — reads `inputs[0][0]` only | treats buffer as flat 1-D | ✅ |
| Chunk size | 1600 samples once `buffer.length >= 1600` (:28-30) = **3200 bytes** | `PCM16_CHUNK_BYTES = 3200` (:10) | ✅ |
| Chunk duration | 0.1 s @16 kHz | `_PCM_CHUNK_SECONDS = 0.1` (:31) | ✅ |
| Scaling | `clamped < 0 ? c*0x8000 : c*0x7FFF` (:24) | `/ 32768.0` (:28) | ⚠ asymmetric |
| Transport | raw binary, no base64, `binaryType="arraybuffer"` | `message["bytes"]` | ✅ |

The critical coupling is **`len % 3200 == 0`**. The worklet emits exactly 1600 samples per message and `ws.send(event.data)` forwards the buffer unmodified, so the invariant currently holds. **[V]** This is an undocumented, un-negotiated, brittle equality — see R-04.

**[V]** `Int16Array` → `ArrayBuffer` is native-endian; the server hard-codes `<i2` (little-endian). Correct for x86/ARM browsers **[I]**; a big-endian platform would silently produce noise, with no detection path.

### The WebM branch is dead for this client **[V]**

`_WEBM_CHUNK_SECONDS = 1.5` and the `else:` branch ([emotion_stream.py:207-235](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/emotion_stream.py#L207)) plus `analyze_audio_chunk()` exist to decode container chunks via a temp `.webm`. The only frontend socket producer is the PCM worklet, which never sends a container frame. WebM reaches the backend **only** over HTTP multipart (`useMediaRecorder`, `video/webm;codecs=vp9,opus` / `vp8` / `video/webm`, `recorder.start(250)`). **[V]** So the WS WebM path is unreachable legacy surface.

---

## 4. JSON control-message contract

Multiplexing is done by `websocket.receive()` and the presence of the `bytes` key ([emotion_stream.py:103-127](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/emotion_stream.py#L103)) — **binary ⇒ audio, text ⇒ control**. Both frame classes arrive on the same unordered stream with no sequence numbers.

### 4.1 Inbound: `context` (client → server)

Server accepts, after `.strip()`:

| Text frame | Server action |
|---|---|
| `"close"`, `"stop"`, `"end"` (any case) | `break` — end session |
| `""` / whitespace | `continue` (ignored) |
| non-JSON | `JSONDecodeError` → `continue` — **silently dropped, no error returned** |
| JSON object with `type != "context"` | `continue` — **silently dropped** |
| JSON with `type == "context"` | reads `partial_transcript`, `question`, `category` |

```python
if context.get("partial_transcript") is not None: partial_transcript = str(context["partial_transcript"])
if context.get("question"):  question_text = str(context["question"]);  is_guesstimate = True
if context.get("category"):  session_category = str(context["category"]); is_guesstimate = True
```

### 4.2 CRITICAL — `partialTranscript` vs `partial_transcript` **[V]**

Client sends **camelCase** ([useLiveEmotionStream.ts:291-297](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/hooks/useLiveEmotionStream.ts#L291)):

```ts
ws.send(JSON.stringify({ type: "context", category, question, partialTranscript }));
```

The same defect applies to the `onopen` frame, which spreads the camelCase object directly (`{ type:"context", ...contextRef.current }`, :154-157) — `LiveStreamContext.partialTranscript` is declared camelCase at :22.

Server reads **only** `partial_transcript`. Consequences, all provable:

- `partial_transcript` stays `""` for the entire connection lifetime.
- `run_tier2()` calls `generate_tier2_nudge(question_text, "", session_category)` (:82-86) — the Socratic nudge is generated **from the question alone, never from what the candidate actually said**.
- `GuesstimateStudio.tsx:106` feeds `partialTranscript: answerText` — the textarea content is computed, put into React state, sent over the wire, and discarded.
- `category` and `question` **do** match, so tier classification and the tier-1 scaffold still work. The failure is invisible in the UI.

This is the single most important protocol defect in the system: the advertised "Socratic nudges" (commit `326d75e`) are structurally blind to candidate speech.

### 4.3 Outbound events

| Event | Shape | Discriminator | Producers |
|---|---|---|---|
| **Emotion telemetry** | `{confidence:float(1dp), nervousness:float, composure:float, delivery_style:str, pitch_mean_hz:float, pitch_std_hz:float, is_monotone:bool, vocal_tremor:bool, start_sec:float, end_sec:float}` | **NONE** | :293-308, every inference tick |
| `coach_nudge` (tier 1) | `{type:"coach_nudge", tier:1, message:str}` | `type` | :145-153, guesstimate only |
| `coach_nudge` (tier 2) | `{type:"coach_nudge", tier:2, message:str}` | `type` | :98 (inside `run_tier2`) |
| `clear_nudge` | `{type:"clear_nudge"}` | `type` | :142 |

**[V] Protocol inconsistency (R-05):** the highest-frequency frame — the one that drives the live HUD — carries **no `type` field**, while the three low-frequency control frames do. The client compensates with structural detection: `if (typeof data?.confidence === "number")` (:183). Correct today; silently breaks if a nudge frame ever gains a numeric `confidence`, and any future event must remember to keep `confidence` absent.

**[V] Not sent, despite existing server-side:** `arousal`, `valence`, `dominance`, `dynamic_range_semitones`, `vocal_jitter_percent`, `vocal_shimmer_percent`, `hnr_db`, `delivery_clarity`, `weight`. These are all computed and written into the Redis point (:257-282) but **stripped from the wire frame**. The frontend's `VocalDeliveryTimelinePoint`/`VocalProsodyMetrics` types model them — they arrive only post-hoc through the HTTP report, never live.

### 4.4 Outbound frame order is not guaranteed **[V → I]**

`send()` serialises writes with `asyncio.Lock` (:75-77), so frames cannot interleave mid-write. But telemetry sends happen **inline in the receive loop**, while `coach_nudge` tier-2 sends happen from a detached `asyncio.create_task`. A tier-2 nudge can therefore be delivered before, between, or after telemetry frames relative to the stall that produced it, and a `clear_nudge` can overtake the `coach_nudge` it is meant to cancel.

---

## 5. Session initialisation & termination

| Concern | Reality | Tag |
|---|---|---|
| WS opened before DB session exists | **Yes for JAM** — the socket is bound to literal `0`; the DB row is created only in `handleUpload()` **after** recording stops | [V] |
| Server validates `session_id` exists | No. `db.get()` returning `None` yields `(None, None)` ⇒ `is_guesstimate=False`; socket proceeds happily | [V] |
| Server validates caller owns `session_id` | No — and cannot, since no identity is captured | [V] |
| Graceful end-of-session message | None in either direction | [V] |
| Buffer flush on disconnect | **None.** `finally` (:313-319) does not drain. Draining happens only in HTTP routes | [V] |
| Reconnect | **None.** `onclose`/`onerror` only `setIsConnected(false)` (:164-165). A dropped socket stays dead until `isRecording` toggles | [V] |
| Heartbeat / ping-pong | No application-level keepalive anywhere. Relies on uvicorn/starlette defaults, which are not configured in code (`uvicorn.run("main:app", …, reload=True)` at :132) | [V]/[U] |
| Idle timeout | None; a silent mic still advances nothing, and the loop just blocks on `receive()` | [V] |

**[V]** `resolveWsBase()` reads `localStorage["speakflow_api_url"]` at connect time, so the WS host can diverge from the `apiClient` baseURL captured at axios-module load; both are re-read per request via the axios interceptor, so in practice they track each other.

---

## 6. Server-side processing pipeline per binary frame **[V]**

```
binary frame (3200 B)
  └─ is_pcm16_chunk → True
      ├─ IF is_guesstimate:
      │     await asyncio.to_thread(process_laya_chunk, session_id, payload, 0.1)
      │       → {is_speaking, stall_seconds, trigger_tier, rebound}
      │       is_speaking   → cancel tier2_task; if hint_active → send clear_nudge
      │       trigger_tier=1→ send coach_nudge(tier1, static CATEGORY_SCAFFOLDS[category])
      │       trigger_tier=2→ asyncio.create_task(run_tier2())   # fire-and-forget
      └─ np.frombuffer("<i2")/32768 → pcm_window.extend(float32)   # deque maxlen 32000 = 2 s
         elapsed = round(elapsed + 0.1, 2)
         GATE: (monotonic() - last_inference < 1.0 s) OR (len(pcm_window) < 16000) → CONTINUE
         window_audio = np.array(pcm_window)                        # trailing 2 s
         prosody_result = await to_thread(extract_prosody_features, window_audio)   # Praat/Parselmouth
         result         = await to_thread(analyze_audio_waveform, window_audio, prosody=…)  # audEERING
         EMA-smooth confidence/nervousness/composure (α=0.35)
         point = {start_sec,end_sec,confidence,nervousness,composure,arousal,valence,dominance,
                  pitch_mean_hz,pitch_std_hz,dynamic_range_semitones,is_monotone,
                  vocal_jitter_percent,vocal_shimmer_percent,hnr_db,vocal_tremor,
                  delivery_clarity,weight}
         await to_thread(buffer_emotion_point, session_id, point)   # Redis RPUSH + EXPIRE 3600
         send({EMA telemetry frame})
```

Cadence: inference at **≤1 Hz**, on a **2 s sliding window**, fed by **10 Hz** frames. Worst case one inference behind.

**Timing model defect [V]:** `elapsed += _PCM_CHUNK_SECONDS` charges a **fixed 0.1 s** per frame regardless of the frame's actual byte length. A 6400-byte frame (legal: `6400 % 3200 == 0`, 0.2 s of audio) is charged 0.1 s — so `start_sec`/`end_sec` and `weight` drift by the ratio of actual to assumed frame size. `weight` feeds the weighted average in the final report, so drift propagates into persisted scores.

**Error handling [V]:** prosody failure → `empty_prosody()` (zeros, `delivery_clarity="Clear"`); emotion failure → `result = {}` → all three scores fall back to defaults `50/50/60` (:240-242). **Neither condition is ever reported to the client.** A dead model or missing Parselmouth yields a plausible, flat, confidently-worded telemetry stream.

---

## 7. Where telemetry, emotion, transcripts and coaching reach the UI

| Data | Live path | Post-hoc path | Tag |
|---|---|---|---|
| Emotion/confidence HUD | WS frame (no `type`) → `setLiveEmotion` → `LiveConfidenceNeedle` / `LiveCoachNudge` | `report.vocal_delivery` → `VocalDeliveryCard` | [V] |
| Persisted emotion timeline | WS → `buffer_emotion_point` → Redis `emotion:session:{id}` (RPUSH + `EXPIRE 3600`, JSON strings, `decode_responses=True`) | `get_session_emotion_summary(session_id)` → `LRANGE 0 -1` + `DELETE` (atomic pipeline) → `_summarize_points` weighted by `point["weight"]` | [V] |
| Who drains | **Guesstimate** at submit ([guesstimate.py:175](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/guesstimate.py#L175)); **HR** only on the final question ([hr.py:205](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/hr.py#L205)); **Technical** only on completion ([technical.py:348](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/technical.py#L348)); **JAM never** | — | [V] |
| Transcript | **No live transcript channel exists.** WS carries audio *up* only | `transcribe_audio()` post-hoc, whole-file Faster-Whisper, `asyncio.to_thread` | [V] |
| Coaching nudges | WS `coach_nudge` / `clear_nudge` → `LiveCoachNudge` (Guesstimate only) | `report.laya_metrics` | [V] |
| Nonverbal / CV | **Nothing live.** `useFaceTracking` output (`faceDetected`, `centered`) drives a UI badge only and is never transmitted | `analyze_video` → `multimodal_tracker.analyze_multimodal_stream` (MediaPipe) during `POST /analyze` | [V] |
| Redis-down fallback | `_LOCAL_BUFFERS: Dict[int, List[dict]]` in-process, capped 5000 points; `_mark_redis_down` + 30 s re-probe | **[I]** If uvicorn runs `workers>1`, WS worker and HTTP worker differ and local points are invisible → report silently uses `fallback`/neutral | [V]/[I] |

**[V] JAM telemetry is written and never read.** `RecordingSession` binds the socket to `session_id=0`, so every JAM round in history appends points to the single Redis key `emotion:session:0`. `routes/analysis.py` never calls `get_session_emotion_summary` (grep-confirmed: only hr/technical/guesstimate do). Net effect: an unbounded cross-session accumulator that is discarded, and — because the key is refreshed to TTL 3600 on every write — it is effectively never evicted while the app is in use.

---

## 8. Proven races, protocol inconsistencies and format risks

Ordered by demonstrated severity. Full remediation in `ARCHITECTURE_RISKS.md`.

| ID | Finding | Evidence | Provable? |
|---|---|---|---|
| **R-01** | JAM opens the WS with a hardcoded `sessionId = 0`, before any DB session exists; telemetry is buffered under `emotion:session:0` forever and never drained. | [RecordingSession.tsx:23-28](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Recording/RecordingSession.tsx#L23); drain-site grep | **[V]** |
| **R-02** | `partialTranscript` (client) ≠ `partial_transcript` (server) ⇒ Laya tier-2 is always generated from an empty transcript. | [useLiveEmotionStream.ts:296](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/hooks/useLiveEmotionStream.ts#L296) vs [emotion_stream.py:119](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/emotion_stream.py#L119) | **[V]** |
| **R-03** | `run_tier2` sends *outside* its `try/except`; `finally` cancels the task and closes the socket without awaiting it ⇒ `send()` on a closing socket raises inside an unretrieved task; `hint_active` is set *after* the await, so the state machine can cancel a task that never set it, or fire a duplicate tier-2. | :79-99 vs :141-158 vs :313-317 | **[V]** (structure) |
| **R-04** | Audio format is inferred from `len % 3200 == 0`; a 10 ms gap, a coalesced write, or a non-multiple chunk silently re-routes PCM into the WebM decoder. No error is ever surfaced. | audio_pcm.py:14-19 | **[V]** |
| **R-05** | Telemetry frame has no `type`; the client discriminates on `typeof data.confidence === "number"`. | :293-308 vs hook :183 | **[V]** |
| **R-06** | `elapsed` charges fixed 0.1 s/frame irrespective of real byte length ⇒ timestamp and `weight` drift into persisted reports. | :130, :164 | **[V]** |
| **R-07** | No auth, no ownership check, no rate limit on the socket; any client can attach to any `session_id` and pollute its emotion buffer. | :54-56 | **[V]** |
| **R-08** | No reconnect; `onclose`/`onerror` only clear a flag; the socket is not reopened until `isRecording` flips. | hook :164-165, deps :280 | **[V]** |
| **R-09** | Unlocked mutation of module globals `_REDIS_CLIENT/_REDIS_AVAILABLE/_REDIS_LAST_CHECK` and `_LOCAL_BUFFERS` from multiple `asyncio.to_thread` workers (check-then-set + read-modify-trim). | emotion.py:462-551 | **[V]** (unsynchronised) / **[I]** (harm) |
| **R-10** | One cached HF `wav2vec2-large` instance is invoked concurrently from WS and HTTP threads under `torch.no_grad()`; thread-safety of a shared model is not guaranteed. | emotion.py:23-65 + `to_thread` at :189/:209 | **[I]** |
| **R-11** | `workletNode.connect(audioCtx.destination)` routes the live mic to the speakers — audible side-tone/feedback, and any microphone speaker output re-enters the analyser. | hook :255 | **[V]** (code) / **[I]** (acoustic effect) |
| **R-12** | Browser resamples 48→16 kHz by naive linear interpolation with no anti-alias filter; >8 kHz energy folds into the band the audEERING model expects to be clean. | audio-processor.js:16-26 | **[V]** (code) / **[I]** (measurement impact) |
| **R-13** | Silent-drop error model: malformed JSON, unknown `type`, failed prosody, failed inference, missing `session_id` — none produce a client-visible error. Degraded analysis looks identical to calm delivery. | :116-127, :180-200 | **[V]** |
| **R-14** | Startup warms the emotion model via `asyncio.create_task` stored on `app.state` but never awaited; the first WS connect can race warm-up. | main.py:98-99 | **[V]** (benign; `_MODEL_LOCK` double-check mitigates) |
| **R-15** | WebM WS branch (`_WEBM_CHUNK_SECONDS`, `analyze_audio_chunk`) is unreachable from the only client — dead protocol surface that still passes code review and consumes maintenance. | :207-235 | **[V]** |

**Not a race (checked):** `_drain_points` issues `LRANGE`+`DELETE` through a redis-py `pipeline()`, whose default is `MULTI/EXEC`, so a concurrent `RPUSH` cannot interleave between read and delete. **[I]** — relies on the library default, not an explicit `transaction=True`.

---

## 9. Caveat on tree state

`git status` at audit time already showed these files **modified and uncommitted before this audit began** (no edit was made by this task): `backend/main.py`, `backend/app/routes/analysis.py`, `backend/app/routes/emotion_stream.py`, `backend/app/services/{emotion,feedback,laya,prosody}.py`, `backend/requirements.txt`, `frontend/src/components/Analysis/AnalysisResults.tsx`, `frontend/src/components/Interview/{LiveConfidenceNeedle,VocalDeliveryCard}.tsx`, `frontend/src/components/Recording/RecordingSession.tsx`, `frontend/src/hooks/useLiveEmotionStream.ts`, `frontend/src/types/index.ts`; plus untracked `backend/app/services/audio_pcm.py` and `frontend/public/`.

**Consequence:** the entire real-time pipeline described here is *uncommitted work in progress*. It has no `HEAD` baseline, so nothing in this document is protected by version history. The `audio_pcm.py` module — which defines the wire contract — is untracked.
