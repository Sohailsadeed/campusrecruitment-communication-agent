# SpeakFlow — Architecture Risks & Contract Inconsistency Register

**Audit date:** 2026-10-31 · **Branch:** `feature/hr-round` @ `326d75e` (+14 modified / 2 untracked pre-existing files)
**Mode:** strictly READ-ONLY. Nothing here has been fixed; no source file was touched.
**Evidence tags:** `[V]` read from source · `[V-live]` verified by executing code / querying the live DB · `[I]` inferred · `[U]` unknown

**Rule applied throughout:** *"Do not report speculative problems as confirmed bugs."* Every finding below states its evidence tag. Where a defect is **latent** — the code path exists and is proven, but the current installed dependency set prevents it firing — that is stated explicitly and the severity reflects the latent risk, not a present outage. `[V-live]` dependency checks were done by importing the packages from the project venv.

Each finding carries the seven mandated fields: **(1) file path (2) function/class/endpoint (3) actual implementation (4) expected behaviour (5) discrepancy (6) potential impact (7) recommended correction.**

---

## Severity totals

| Severity | Count | IDs |
|---|---|---|
| **CRITICAL** | 11 | C-01 … C-11 |
| **HIGH** | 15 | H-01 … H-15 |
| **MEDIUM** | 25 | M-01 … M-25 |
| **LOW** | 12 | L-01 … L-12 |
| **Total** | **63** | |

Cross-references to the per-document registers: `WS R-nn` = `WEBSOCKET_CONTRACT_AUDIT.md §8`; `DB-nn` = `DATABASE_SESSION_AUDIT.md §8`; `J/H/G/T/P-nn` = `MODULE_INTEGRATION_AUDIT.md`.

---

# CRITICAL

---

### C-01 — Auth is advisory, not enforced: every authenticated endpoint silently falls back to a real database user

1. **File:** `backend/app/routes/auth.py:71-95`
2. **Function:** `get_current_user()`
3. **Actual:** `[V]`
   ```python
   def get_current_user(authorization=Header(default=None), db=Depends(get_db)) -> User:
       if authorization and authorization.lower().startswith("bearer "):
           token = authorization.split(" ", 1)[1]
           subject = decode_token(token)
           if subject:
               user = db.scalar(select(User).where(User.email == subject))
               if user: return user
       # Fallback for dev / unauthenticated local use
       user = db.scalar(select(User).order_by(User.id.asc()))
       if not user:
           user = User(email="developer@verbaliq.local", username="candidate",
                       full_name="Alex Rivera", hashed_password=hash_password("verbaliq123"))
           db.add(user); db.commit(); db.refresh(user)
       return user
   ```
   A missing, malformed, expired, or signature-invalid token all take the **same** path: return the lowest-id user in the table, or create one.
4. **Expected:** an unauthenticated or invalid request gets 401 before any handler runs.
5. **Discrepancy:** `get_current_user` — the dependency every round router imports as *the* auth gate — never raises. Only `GET /api/auth/me` behaves correctly (`auth.py`, strict 401), which makes the exception prove the rule. There are additionally **four incompatible identity resolvers** in the codebase (`get_current_user`, `get_optional_current_user`, `_get_optional_user` in `sessions.py:67`, and `_resolve_user_id` in `coach.py:39`), and `progress.py`/`coach.py` import the third. `[V]`
6. **Impact:** the entire multi-user boundary is nominal. Anyone reaching the port can read and write user 1's sessions, HR/Technical/Guesstimate state, resume, curriculum plan, and dashboard — no token required. `App.tsx:69` gates every route behind `ProtectedRoute`, so the *frontend* implies real auth while the *backend* ignores it. This is the root cause that promotes several findings below from "privilege escalation" to "unauthenticated remote access".
7. **Correction:** split the dependency into `get_current_user` (raises 401) and `get_optional_current_user` (returns `None`); delete the auto-create branch; make the guest fallback opt-in via an explicit `settings.allow_anonymous_local_drills` flag defaulting to `False`; converge the four resolvers on one; add a FastAPI middleware or `TestClient` assertion suite that hits every non-public route without a header and expects 401.

---

### C-02 — `POST /api/sessions/{id}/analyze` has no identity dependency whatsoever

1. **File:** `backend/app/routes/analysis.py:86-92`
2. **Endpoint:** `analyze_session()` — `def analyze_session(session_id: int, db: Session = Depends(get_db), …)`
3. **Actual:** `[V]` the signature takes `session_id` and `db` only. There is no `current_user`, no `Depends(get_current_user)`, and no `_get_session_for_user` call. It additionally has **no `round_type` guard**, so it is invocable against an HR, Technical, or Guesstimate session id.
4. **Expected:** analysis is a mutating, CPU-expensive operation on a user's session and must be ownership-checked and round-scoped.
5. **Discrepancy:** the one endpoint that rewrites `transcriptions`, `session_analyses`, `ai_feedback`, `sessions.overall_score`, `sessions.round_metadata` and `sessions.report`, and the only endpoint that can transition `→ completed`, is completely unauthenticated.
6. **Impact:** (a) unauthenticated denial-of-service — each call runs Whisper + MediaPipe + Parselmouth + a wav2vec2 forward pass + an LLM call **synchronously in the request** (see H-05), so a handful of concurrent requests saturate the single process; (b) data destruction — iterating session ids overwrites every user's report; (c) cross-round corruption — analysing an HR session stamps a JAM-shaped `report` onto it, after which `HRReport.tsx` finds no `strengths`/`weaknesses` (see M-14).
7. **Correction:** add `current_user = Depends(get_current_user)` and route the fetch through the same ownership helper used by `/audio`; reject with 409 when `session.round_type != "jam"`; make re-analysis an explicit `?force=true` opt-in.

---

### C-03 — HR and Technical answer endpoints resolve a user and then never use it for authorization

1. **Files:** `backend/app/routes/hr.py:111-120`, `backend/app/routes/technical.py:232-…`
2. **Endpoints:** `submit_hr_answer()`, `submit_technical_answer()`
3. **Actual:** `[V]` both declare `current_user: User = Depends(get_current_user)` and then load the row with a bare
   ```python
   session = db.get(SessionModel, session_id)      # hr.py:120
   ```
   with no `session.user_id` comparison. The same pattern repeats in `/session/{id}` (`hr.py:240`) and `/report/{id}` (`hr.py:268`).
4. **Expected:** every round-state fetch goes through an ownership check equivalent to `_get_session_for_user` (`routes/sessions.py`).
5. **Discrepancy:** the dependency is decorative — it exists, is imported, is never consulted.
6. **Impact:** writing another candidate's answers into their HR/Technical interview, and reading their transcripts, STAR scores and per-question audio. Combined with C-01 the "other candidate" needs no credential at all.
7. **Correction:** introduce one `load_owned_session(session_id, current_user, db)` helper, use it in all three round routers, and assert `session.user_id == current_user.id` in every handler that both reads and writes round state.

---

### C-04 — `GET /api/technical/audio/{filename}` is unauthenticated and filename-addressable

1. **File:** `backend/app/routes/technical.py:435-445`
2. **Endpoint:** `stream_technical_audio(filename: str)`
3. **Actual:** `[V]`
   ```python
   @router.get("/audio/{filename}")
   def stream_technical_audio(filename: str):
       safe_name = Path(filename).name
       file_path = settings.upload_dir / "technical_audio" / safe_name
       if not file_path.exists(): raise HTTPException(404, …)
       return FileResponse(file_path, media_type="audio/webm")
   ```
   No user dependency. `Path(filename).name` does correctly neutralise traversal. Compare `hr.py:288-292`, the same endpoint in the sibling module, **which does** require `Depends(get_current_user)` — and `sessions.py`, which uses an id-based, ownership-checked `/api/sessions/{id}/audio`.
4. **Expected:** candidate answer audio is personal speech data and must be served only to its owner.
5. **Discrepancy:** three audio endpoints, three different authorization models; the Technical one is the only fully open one.
6. **Impact:** any unauthenticated client can enumerate or guess filenames under `upload_dir/technical_audio` and download recorded interview answers. Filenames are server-generated, so exposure depends on id randomness rather than on an access check.
7. **Correction:** delete this endpoint and serve Technical audio through the ownership-checked session-audio route; if a filename route must remain, add `Depends(get_current_user)` and verify the file's owning session belongs to that user.

---

### C-05 — Coach authorization contains a hardcoded `user_id != 1` bypass

1. **File:** `backend/app/routes/coach.py:189-192` (and `_resolve_user_id`, `coach.py:39`)
2. **Endpoint:** `get_plan` / `complete_day` ownership check
3. **Actual:** `[V]`
   ```python
   user_id = _resolve_user_id(current_user)          # None → 1
   if not plan or (plan.user_id and plan.user_id != user_id and user_id != 1):
       raise HTTPException(status_code=404, detail="Curriculum plan not found")
   ```
4. **Expected:** `plan.user_id != user_id` → 404, unconditionally.
5. **Discrepancy:** the `and user_id != 1` clause exempts user 1 from every ownership check, and `_resolve_user_id(None) → 1` means **an unauthenticated caller resolves to user 1 and therefore receives the bypass**. The second hole is `plan.user_id` being falsy: a plan row with `user_id IS NULL` skips the check for everyone.
6. **Impact:** with C-01 in front of it, `GET /api/coach/active` and `POST /api/coach/complete` read and mutate any user's curriculum plan anonymously.
7. **Correction:** remove the `user_id != 1` clause; make `_resolve_user_id` raise 401 instead of defaulting to 1; treat `plan.user_id IS NULL` as denied rather than as public.

---

### C-06 — Live `partial_transcript` is never delivered: the client sends camelCase, the server reads snake_case

1. **Files:** `frontend/src/hooks/useLiveEmotionStream.ts:291-297` → `backend/app/routes/emotion_stream.py:69,119-120`
2. **Functions:** the second context `useEffect`; the WS `context` branch
3. **Actual:** `[V]` both ends.
   ```ts
   ws.send(JSON.stringify({ type: "context", category, question, partialTranscript }));
   ```
   ```python
   if context.get("partial_transcript") is not None:
       partial_transcript = str(context["partial_transcript"])
   ```
   `partial_transcript` is initialised to `""` at `:69` and, absent the key, never reassigned.
4. **Expected:** the Socratic tier-2 hint is conditioned on what the candidate has said so far.
5. **Discrepancy:** **the only module with a working live-coach loop never gets its transcript half.** Note `question` and `category` — sent with matching names on both sides — *do* arrive, and are additionally seeded server-side independently of the client by `_load_guesstimate_context` (`emotion_stream.py:37-51,65-67`), which reads `case.category` / `case.question` straight from `guesstimate_cases` when `round_type == "guesstimate"`. So the prompt's *question* half is robustly populated from two sources, while `partial_transcript` has **no** server-side source and is broken by one key name. `[V]` The mismatch produces no error anywhere.
6. **Impact:** `generate_tier2_nudge(question, "", category)` (`services/guesstimate/nudge_service.py:99`) builds its prompt with an always-empty evidence field, so tier-2 hints are generic rephrasings of the tier-1 scaffold rather than targeted interventions. Silent, total loss of the product's headline differentiator. The DB seeding means the failure is invisible in testing too — hints *do* appear, they are simply not about what the candidate said.
7. **Correction:** send `partial_transcript` (or read both spellings server-side) and add a contract test that asserts the server's `partial_transcript` variable is non-empty after a context frame. Long-term: define one shared message schema (`schemas/ws.py` Pydantic models + a generated TS type) rather than hand-matching keys.

---

### C-07 — HR/Technical per-question state is a JSON array read-modify-written with no lock, no version, no `flag_modified`

1. **Files:** `backend/app/routes/hr.py:186-189`; same pattern in `routes/technical.py`
2. **Endpoint:** `submit_hr_answer()`
3. **Actual:** `[V]`
   ```python
   updated_questions = list(hr.questions or [])
   updated_questions.append(completed_question)
   hr.questions = updated_questions
   hr.question_count = len(updated_questions)
   ```
   The fetch is `db.get(SessionModel, session_id)` with no `with_for_update()`, no optimistic-version column, and no transaction isolation above the default.
4. **Expected:** appending to a shared aggregate is either serialised (row lock) or guarded (version check), so a lost write fails loudly.
5. **Discrepancy:** two concurrent `/api/hr/answer` POSTs for the same session both read `questions = [q1]`, both compute `[q1, q2]` / `[q1, q3]`, and the later commit overwrites the earlier. `question_count` is then *derived from the overwritten array*, so even the counter hides the loss.
6. **Impact:** a submitted answer — its transcription, its STAR evaluation, and its audio path — disappears with HTTP 200 and no log line. Because the completion decision is `question_count >= max_questions`, a lost write can also make a 4-question interview finish at 3, or never finish.
7. **Correction:** `select(HRInterview).where(...).with_for_update()` inside the handler, or move `questions` out of JSON into a child table (`hr_answers`) so appends are INSERTs; failing both, add a `revision` integer with a `WHERE revision = :expected` compare-and-set and 409 on mismatch.

---

### C-08 — JAM live emotion is written to a session id that does not exist and read by nobody

1. **Files:** `frontend/src/components/Recording/RecordingSession.tsx:22` → `backend/app/routes/emotion_stream.py:54` → `backend/app/services/emotion.py:471-472,513,710`
2. **Functions:** `useLiveEmotionStream(0, isRecording, undefined, recorder.stream)`; `_buffer_key()`; `buffer_emotion_point()`; `get_session_emotion_summary()`
3. **Actual:** `[V]` JAM opens `/ws/session/0/emotion` for the whole recording because the DB row is only created after upload (`handleUpload` → `uploadSession` → `analyze`). Redis accumulates under `emotion:session:0` with `EXPIRE 3600`. The real id returned by `POST /api/sessions` is never associated with that key, and `routes/analysis.py` — which imports `analyze_speech_emotion` and `extract_prosody_features` — **never imports or calls `get_session_emotion_summary`** (grep-confirmed). `[V]`
4. **Expected:** live vocal telemetry recorded during a JAM round is available to that round's report, as it is for HR/Guesstimate/Technical.
5. **Discrepancy:** three separate breaks in one flow — wrong id at connect, no id migration, no reader.
6. **Impact:** JAM's `LiveConfidenceNeedle` is real but ephemeral and unreported. Every JAM vocal-delivery number on the report page comes from the *post-hoc* file analysis, and the 1 Hz live stream that the user watched is destroyed. All JAM live data across all users additionally collides on the single key `emotion:session:0`.
7. **Correction:** create the session row **before** recording starts (a `POST /api/sessions/intent` that returns an id), pass that id to the hook, and have `/analyze` call `get_session_emotion_summary(session_id, fallback=…)`. Add a WS-path test asserting the buffer key equals the id the eventual report reads.

---

### C-09 — Fabricated nonverbal metrics are presented as measurements

1. **Files:** `backend/app/services/multimodal_tracker.py` (`_deterministic_fallback`) · `backend/app/routes/analysis.py:248-254,263-267,289-293`
2. **Functions:** `analyze_multimodal_stream()`, `_deterministic_fallback()`, `analyze_session()` except-path
3. **Actual:** `[V]`
   ```python
   rng = random.Random(abs(hash(str(video_path) or "verbal_iq_seed")))
   ec_overall        = round(rng.uniform(76.0, 92.0), 1)
   posture_overall   = round(rng.uniform(80.0, 94.0), 1)
   "hand_gestures_count": rng.randint(2, 6), "fidget_count": rng.randint(0, 2)
   ```
   returned whenever MediaPipe/OpenCV is unavailable **or the video file is missing/unopenable**. Separately, the analysis exception path hardcodes `eye_contact_percentage 82.0`, `posture_quality 85.0`, `prosody_confidence 84.0`, `vocal_energy_db -22.0`, `tone_verdict "Measured & Structured"`, a `congruence` object `{"status": "High Alignment", "analysis": "Nonverbal delivery matched spoken messaging."}` and a full `avatar_reaction` `{"expression": "empathic_nod", "gesture": "open_palm_welcome", "timing": "00:02"}`.
4. **Expected:** absence of a camera analysis is reported as absence.
5. **Discrepancy:** invented values are written into `session_analyses.eye_contact_percentage` / `.posture_quality` and into `sessions.report.congruence` / `.avatar_reaction`, indistinguishable in the DB from real measurements. `[V]` The report page renders them with no provenance marker (`AnalysisResults.tsx:1098-1114`).
6. **Latency note:** `[V-live]` `mediapipe 0.10.13` **is** installed in the project venv, so the fallback does not fire in the current environment — this is a latent, not an active, fabrication. It becomes active on any deployment where the headless OpenCV/MediaPipe wheel fails to install (a common ARM/Windows event) or where the video file is absent.
7. **Impact:** a hiring-readiness product telling a candidate they held 82 % eye contact and showed "High Alignment" when nothing was measured. It also corrupts the aggregate dashboard, since `progress.py` averages those columns into the readiness score.
8. **Correction:** return `None`/`available: false` from the fallback and propagate `null` to the schema; render "not measured" in the UI; never write a default into `session_analyses`; if deterministic demo data is wanted for a studio mode, gate it behind an explicit `settings.demo_mode` and stamp `"_synthetic": true` into the payload so consumers can filter it.

---

### C-10 — Fabricated transcripts with a fake confidence score

1. **File:** `backend/app/services/transcription.py` (`MOCK_TRANSCRIPTS`, `transcribe_audio`, `_get_faster_whisper_model`)
2. **Function:** `transcribe_audio(audio_path, model_name="small", allow_mock=True)`
3. **Actual:** `[V]` the chain is Faster-Whisper → openai-whisper → mock. On total failure with `allow_mock=True`:
   ```python
   seed = abs(hash(str(audio_path) or "default"))
   rng  = random.Random(seed)
   text = rng.choice(MOCK_TRANSCRIPTS)
   …
   return {"text": text, "language": "en", "confidence": 0.88,
           "words": mock_words, "segments": mock_segments, **pause_info}
   ```
   with synthetic `pause_gap = rng.choice([0.1, 0.1, 0.6, 0.8])`. The two real paths also hardcode their confidence: **0.94** for Faster-Whisper and **0.90** for openai-whisper — neither is a measured quantity.
4. **Expected:** `confidence` is a model-derived estimate; a failed transcription is empty or an error.
5. **Discrepancy:** `transcriptions.confidence` is persisted to a NOT NULL float column and surfaced at `AnalysisResults.tsx:1188` as `Math.round(session.transcription.confidence * 100)` with a "%" suffix. Three of the three confidence values in the file are constants.
6. **Latency note:** `[V-live]` `faster_whisper 1.2.1` **is** installed, so the mock branch is dormant today. The **hardcoded 0.94 / 0.90 are live** — every JAM report shows a fabricated confidence percentage right now.
7. **Impact:** all downstream scoring that consumes `confidence` (and the user's trust in the transcript) rests on a constant. Under the mock branch, a candidate is *graded on a script from a list* — filler counts, pace, pauses, clarity and the LLM feedback all derive from invented text.
8. **Correction:** compute confidence from Whisper's real logprobes (`avg_logprob` / `no_speech_prob`, both already returned by the model) or drop the field; return `_empty_transcription()` unconditionally in non-demo mode; if mock output is kept for studio demos, persist `confidence = None` and add a `source` column (`"faster_whisper" | "whisper" | "mock"`).

---

### C-11 — `"developing"` placement status is emitted by the backend but unrepresentable in the frontend

1. **Files:** `backend/app/routes/progress.py:631` · `frontend/src/api/analysis.ts:275` · `frontend/src/components/Dashboard/PlacementReadinessMatrix.tsx:30-52,119-124`
2. **Endpoint/component:** `placement_readiness()` → `getStatusBadge(status)`
3. **Actual:** `[V]` all three.
   ```python
   "status": "ready" if is_guess_ready else (
       "in_progress" if (latest_guess and len(guesstimate_completed) == 0) else (
       "developing"  if latest_guess else "not_attempted")),
   ```
   ```ts
   status: "ready" | "in_progress" | "not_attempted";      // api/analysis.ts:275
   case "not_attempted":
   default:  return { label: "Unattempted", icon: "radio_button_unchecked", … };
   ```
   `developing` requires ≥1 completed guesstimate AND not-ready — `[V-live]` the audited DB holds **2 completed guesstimate sessions**, so this state is reachable with today's data, not hypothetically.
4. **Expected:** every status the provider can emit is representable by the consumer.
5. **Discrepancy:** a four-value producer enum against a three-value consumer union, with a `default:` arm that maps the unknown value to its **semantic opposite**. TypeScript cannot help: the value arrives as runtime JSON, so the union is a comment.
6. **Impact:** on the placement-readiness dashboard — the product's headline deliverable — a candidate who has attempted and completed guesstimate rounds is told **"Unattempted"**, with the empty-circle icon and the dimmed `opacity-90` card class. The switch even uses the string `"Developing"` as the label for the `in_progress` arm (`:40`), so the vocabulary exists on both sides and simply failed to meet.
7. **Correction:** add `"developing"` to the union and to a `case`; more durably, generate the TS union from the backend (single source of truth: a Python `Enum` → OpenAPI `components/schemas` → `openapi-typescript`), and change the `default:` arm to render the raw string with a neutral "Unknown state" style plus a `console.warn`, so an unmapped enum value is visible rather than wrong.

---

# HIGH

---

### H-01 — The WebSocket accepts binary frames it cannot reliably classify: `is_pcm16_chunk` is a heuristic, not a format check

- **File / function:** `backend/app/services/audio_pcm.py:9-24` (`is_pcm16_chunk`, `decode_pcm16_chunk`); consumer `routes/emotion_stream.py:129-130`. `[V]`
- **Actual:** `return len(audio_bytes) % PCM16_CHUNK_BYTES == 0` after rejecting five container magics (`\x1aE\xdf\xa3`, `RIFF`, `OggS`, `fLaC`, `ID3`). A WebM/Opus fragment that happens to be a multiple of 3200 bytes and does not begin with a magic is **classified as PCM and decoded as noise**. Conversely a 1600-sample flush split across two TCP frames is rejected and re-routed to the WebM decoder.
- **Expected:** the wire format is negotiated at handshake (a text `init` frame declaring codec/rate/channels), and unrecognised bytes are a protocol error, not a silent reclassification.
- **Impact:** intermittent, undiagnosable telemetry corruption or loss, with no log line either way. Note the two branches are **not** cost-equivalent — see M-25. `[I]` for frequency, `[V]` for the heuristic and for the branch asymmetry.
- **Correction:** send an explicit `{type:"init", format:"pcm_s16le", sample_rate:16000, channels:1}` frame before any audio; treat binary without a prior init as protocol error 1008; drop the modulo check.
- Cross-ref: WS R-03, R-04, R-15.

### H-02 — The WebSocket accepts before authenticating, and the `session_id` it looks up is used only for feature gating, never for ownership

1. **File:** `backend/app/routes/emotion_stream.py:54-56` (and `_load_guesstimate_context`, `:37-51`)
2. **Endpoint:** `emotion_websocket(websocket, session_id: int)`
3. **Actual:** `[V]` `await websocket.accept()` is the **first** statement. The only database access is `_load_guesstimate_context(session_id)`, which reads `Session.round_type` to decide whether to enable the Laya loop — it discards `session.user_id` and returns `None, None` for every non-guesstimate round (so for JAM/HR/Technical **no DB read influences access at all**). Failures there are swallowed into `logger.warning`.
4. **Expected:** reject (close code 1008) before accepting when the bearer token is absent/invalid or the session does not belong to the caller.
5. **Discrepancy:** the socket has neither a credential check nor an ownership check, and unlike REST it is not even protected by CORS — browsers do not apply CORS to WebSocket.
6. **Impact:** unauthenticated clients can open sockets on arbitrary ids, and can write emotion/Laya points into any `emotion:session:{id}` buffer that a legitimate later `/submit` then **drains and publishes as that candidate's `vocal_delivery`** — telemetry injection into someone else's scored report. A non-existent id (e.g. `999999`) yields a fully working telemetry stream, which is exactly how JAM ends up using id `0` (C-08).
7. **Correction:** validate the credential at handshake (query param or `Sec-WebSocket-Protocol`, since browsers cannot set an `Authorization` header on `WebSocket`), then `db.get(SessionModel, session_id)` and compare `user_id` **before** `accept()`; add an `Origin` allow-list matching `config.py`'s CORS hosts.
- Cross-ref: WS R-01, C-08.

### H-03 — No reconnect and no heartbeat: a dropped socket silently ends live coaching, and the server's terminator verb is never used

- **Files:** `frontend/src/hooks/useLiveEmotionStream.ts` (`onclose`/`onerror` → `setIsConnected(false)`, nothing else); `backend/app/routes/emotion_stream.py:110` accepts the raw text `"close"|"stop"|"end"` as a graceful terminator but **no client ever sends it**, and the `finally` block (`:313-319`) performs no flush; no server ping/pong. `[V]`
- **Expected:** exponential-backoff reconnect within the recording window, an application-level heartbeat, and a stop signal that flushes the residual window before closing.
- **Impact:** one transient network blip permanently disables the confidence HUD and the Laya stall detection for the rest of the round, with no UI indication. The residual sub-1-second window is never analysed even on a clean client close, and because the terminator verb is unused the backend only learns the round ended via `WebSocketDisconnect`, so `_LAYAS` entries and Redis buffers linger until TTL/pop-on-read.
- **Correction:** client reconnect with backoff + last-sequence resume; server `send_json({"type":"ping"})` every ~5 s; have `stop()` send the existing `"end"` verb (the server branch is already written) and flush there.
- Cross-ref: WS R-06, R-07.

### H-04 — Three client terminals are unhandled: `is_complete=false` with `next_question=null` is a silent no-op

- **Files:** `frontend/src/pages/hr/HRStudio.tsx:245-256`, `frontend/src/pages/technical/TechnicalStudio.tsx:336-348`; providers `routes/hr.py:186-215`, `routes/technical.py`. `[V]`
- **Actual:** `if (res.is_complete && res.report) navigate … else if (res.next_question) advance …` — with **no `else`**. Any reply where neither branch holds resets `isSubmitting` and leaves the screen unchanged.
- **Expected:** every response shape produces either a state change or a visible error.
- **Impact:** the most damaging variant is real: the server has already recorded the answer and incremented `question_count` (`hr.py:189`), so the user sees the *same* question and can re-submit it, appending a duplicate. Because `question_count = len(questions)`, the round then over-counts.
- **Correction:** add a terminal `else` that raises the error banner and re-fetches `GET /{module}/session/{id}` to resynchronise; server-side, make "no next question and not complete" an impossible response (500) rather than a legal one.

### H-05 — `analyze_session` runs the full ML pipeline synchronously inside the request, holding the DB connection and the event loop

- **File:** `routes/analysis.py:86-…` — a plain `def` (threadpool) that sequentially executes `transcribe_audio` → `analyze_transcription` → `analyze_video` → `analyze_audio_prosody` → `analyze_speech_emotion` → `extract_prosody_features` → `generate_feedback`. `[V]`
- **Expected:** long analysis is a job: enqueue, return 202 with a task handle, let the client poll or receive progress.
- **Impact:** a 60-second JAM clip costs tens of seconds of CPU on one process; `status='processing'` is committed up front but the client's only signal is a 120-second axios timeout (`api/client.ts`). Meanwhile the DB connection is pinned for the whole run, exhausting the default 5-plus-10 SQLAlchemy pool. Two concurrent analyses can stall every WebSocket in the process.
- **Correction:** move to a background task / queue with a status endpoint; at minimum raise the pool, wrap each stage in `asyncio.to_thread`, and stream progress.
- Cross-ref: `create_session`'s blocking `while chunk := file.file.read(1024 * 256)` (`routes/sessions.py:112`) inside an `async def` — same event-loop stall class, on upload instead of analysis (H-14).

### H-06 — `interview_mode` / track vocabulary is never validated; an arbitrary string silently yields questions

- **Files:** `backend/app/services/hr/question_bank.py` (`get_initial_hr_question(track=…)`); `routes/hr.py:59-…`; consumer `HRStudio.tsx:31` (`useState("standard_hr")`), `:430-435`. `[V]`
- **Actual:** `[V-live]` calling `get_initial_hr_question(track='standard_hr')` and `track='totally_bogus'` both return a question — no exception, no 422, no filter effect. The column is `String(50)` with `default='standard_hr'`, no CHECK (`models/hr.py:22`).
- **Expected:** an unknown mode is a 422 and the mode list is a server-owned enum shared with the client.
- **Impact:** mis-spelled modes silently mis-select the question bank, so a "strengths-based" interview receives conflict questions and the report still labels itself with whatever string was posted (`HRReport.tsx:150` `.replace('_',' ')`).
- **Correction:** validate against `get_hr_tracks()` ids in `StartHRRequest` with a Pydantic `Literal`/enum, 422 otherwise, and expose the same enum to the frontend from OpenAPI.

### H-07 — The MediaRecorder → submit race drops recorded audio in HR and Guesstimate

- **Files:** `HRStudio.tsx:230` (`mediaRecorderRef.current.stop()`) then `:243` (`submitHRAnswer(…, recordedAudioBlob)`); `GuesstimateStudio.tsx:298` then `:311-316`. `[V]` ordering; `[I]` browser timing.
- **Actual:** `recordedAudioBlob` is React state set only by the asynchronous `recorder.onstop` (`HRStudio:169-173`); the submit line runs in the same synchronous block as `stop()`, so it reads the value from *before* the click.
- **Expected:** submit awaits the blob.
- **Impact:** submitting while the mic is live uploads **no audio**; the blob then arrives during the `await` and is cleared (`:252`) or orphaned by navigation. Consequences cascade server-side: `transcribe_audio` and `analyze_speech_emotion` are never called for that answer, so per-question `audio_url`/`vocal_delivery` are absent — silently, because `asyncio.gather(..., return_exceptions=True)` tolerates missing input.
- **Correction:** make `stop()` return a `Promise<Blob>` (`recorder.onstop = () => resolve(collect())`) and `await` it before submit; mirror the pattern already used for `useMediaRecorder` in JAM.

### H-08 — Technical never uploads audio at all

- **File:** `frontend/src/pages/technical/TechnicalStudio.tsx:321-324` (submit stops only the recogniser, never `mediaRecorderRef.current.stop()`); `recordedAudioBlob` is nulled on each record start (`:201`) and produced only by `recorder.onstop` (`:214-218`). `[V]`
- **Expected:** as in HR, each answer's audio accompanies the POST.
- **Impact:** systematic, not occasional — per-question `audio_url` and `vocal_delivery` are missing from every Technical report unless the user manually toggles recording off first. `routes/technical.py:337-339` only stamps what it receives, so the server reports success. `[V]`
- **Correction:** call `stop()` and await the blob in `handleSubmitAnswer`, exactly as H-07.

### H-09 — Unauthenticated, unbounded, read-modify-write upload paths

- **Files:** `routes/hr.py:143` (`content = await audio_file.read()`), and the equivalents in `routes/technical.py`, `routes/guesstimate.py`; contrast `routes/sessions.py:_save_upload`, which **does** enforce MIME, extension and `settings.max_upload_size_mb`. `[V]`
- **Expected:** every multipart upload passes the same size/type gate before any bytes are buffered.
- **Impact:** `config.py` sets `max_upload_size_mb = 200` but the three round endpoints ignore it and materialise the whole body in RAM; combined with C-01/C-03 any caller can target any session id. Two concurrent requests are 400 MB.
- **Correction:** reuse `_save_upload` (or a shared `save_validated_upload(file, subdir)`) in all four paths; enforce `Content-Length` before reading; stream to disk in chunks.

### H-10 — `POST /api/sessions/json` lets the client supply `overall_score` and `report`, and stamps `status="completed"`

- **File:** `routes/sessions.py:189-200` (`create_session_json`, `overall_score=payload.overall_score`, report passthrough, immediate completed). `[V]`
- **Expected:** server-computed scores only; a session created from client JSON cannot be "completed" without analysis.
- **Impact:** `[V-live]` sessions **14, 15, 19** are exactly this: `status='completed'`, `overall_score NULL`, `report NULL`, zero transcriptions/feedback/media, `round_metadata={'mode':…}`. `AnalysisPage.tsx:15-21` will not re-analyse them (its guard requires `pending`), so `AnalysisResults.tsx` renders them from hardcoded fallbacks — score 84 (`:120`), derived competencies (`:132-139`), invented rewrites (`:164-173`), invented mastery/drills (`:212-221`), percentile claims (`:225`). A "completed" score a user cannot distinguish from a real one.
- **Correction:** drop `overall_score`/`report` from the request schema; create as `pending`; add a `source` discriminator so the UI can label non-analysed sessions.

### H-11 — `resume/upload` returns success when resume processing failed

- **File:** `routes/technical.py:59-90` — `except Exception as exc: logger.warning(…)` and the endpoint still returns the OK payload. `[V]`
- **Expected:** a failure to chunk/embed the resume is a 500 (or at minimum `{"indexed": false}`), because the Technical round's whole premise is resume-grounded questions.
- **Impact:** the UI shows "Resume linked" (`TechnicalStudio.tsx:102-121` reads only `has_resume`/`resume_name`), while Chroma may hold nothing; every later `retrieve_context` returns empty, questions go generic, and `technical_interviews.resume_context` persists a stale copy of the text. Silent quality degradation with no diagnostic.
- **Correction:** propagate the failure, or return `{has_resume, indexed, chunk_count}` and render the difference.

### H-12 — `DELETE /api/technical/resume` leaves the Chroma collection; `store_performance` runs after `db.commit()`

- **Files:** `routes/technical.py:127-…` (delete), `:354` (Mem0 write after commit). `[V]`
- **Expected:** deleting a resume removes both the DB pointer and the vectors; and any cross-store write either precedes the commit or is in the same transaction/outbox.
- **Impact:** re-uploading the same PDF appends duplicate chunks to a collection that still contains the originals → retrieval returns the candidate's own resume text many times, inflating similarity hits and crowding out other context. A Mem0 failure after commit leaves the DB asserting a performance record that memory does not have.
- **Correction:** call `chroma.delete_collection(user_{id})` in the DELETE handler; move `store_performance` before the commit or wrap both in a compensating try/except that rolls the DB back.
- Cross-ref: DB-10, DB-11.

### H-13 — `POST /api/technical/answer` fabricates `{"score": 7, "feedback": "Good response."}` when the graph returns no evaluation

- **File:** `routes/technical.py:329`. `[V]`
- **Expected:** an unevaluated answer is an error state, not a middling score.
- **Impact:** a 7/10 is appended to `technical_interviews.questions`, averaged into the report, multiplied by 10 in `progress.py`, and displayed as graded feedback. With no LangGraph checkpointer (`services/technical/interview_graph.py`) the graph is rebuilt per request, so a state-reconstruction failure lands precisely here.
- **Correction:** raise 502 and leave the question unanswered, or persist `{"score": None, "unavailable": true}` and render "not evaluated".
- Cross-ref: T-09.

### H-14 — Blocking file I/O and blocking inference inside `async def` handlers stall the event loop for every live session

- **Files:** `routes/sessions.py:112` (`while chunk := file.file.read(1024 * 256)` in an `async def create_session`); `main.py:98-108` — the emotion warm-up is `asyncio.create_task(asyncio.to_thread(_load_model))` stored on `app.state.emotion_warmup_task` with a `add_done_callback` that *logs* failure, but **nothing ever awaits it and no request gates on it**. `[V]`
- **Expected:** disk and CPU work off the loop (`to_thread`, or `await file.read(n)`); readiness-dependent traffic gated or delayed until the model is resident.
- **Impact:** a single large upload freezes every open WebSocket's frame processing for its duration, so the confidence needle and Laya stall detection stop mid-round for other users. The un-awaited warm-up means the first emotion inference pays the full HuggingFace model load inside `analyze_audio_waveform`, and because the callback only logs, a *failed* warm-up is indistinguishable from a slow one to the operator — every subsequent inference then returns `_neutral_result()`-class output.
- **Correction:** `await file.read()` in the async handler or make the endpoint a plain `def`; `await` the warm-up task in the lifespan handler and expose a `/health` readiness flag the WS checks before accepting.

### H-15 — `sessions.report` and `round_metadata` are unversioned, multi-writer JSON with four live shapes

- **Files:** `models/session.py:28-29`; writers `routes/analysis.py`, `routes/hr.py`, `routes/technical.py`, `routes/guesstimate.py`, `routes/sessions.py`. `[V]`
- **Actual:** `[V-live]` four `report` shapes (JAM ×3 by commit, HR ×1, Technical ×2 with `summary` → `executive_summary` renamed) and four `round_metadata` shapes (JAM `{}`/8-key/14-key, `{mode}`, `{role,target_company}`, `{}`). No `schema_version`, no migration, no validator.
- **Impact:** detailed in `MODULE_INTEGRATION_AUDIT.md` §3.1/§4.2 — concretely, `TechnicalReport.tsx:111` reads `.summary` so the *current* Technical shape's summary is never displayed, while the *legacy* shape's `avg_*`/`rambling_rate_percent` are absent and `?? 80` / `?? 82` (`:260, :287`) fabricate them. `progress.py` reads JAM-specific metadata keys that are `{}` for HR/Guesstimate/Technical rows.
- **Correction:** introduce a per-round Pydantic report model, a `report_schema_version` int, and a backfill migration; until then, make the readers tolerant *and explicit* (render "unavailable", never invent).
- Cross-ref: DB-04, T-06.

---

# MEDIUM

Each is the same seven fields, compressed to one entry per line-group. `[V]` unless marked.

| ID | File · function | Actual | Expected → discrepancy | Impact | Correction |
|---|---|---|---|---|---|
| **M-01** | `routes/emotion_stream.py` telemetry writer | outbound telemetry frame carries **no `type` key**, while `coach_nudge`/`clear_nudge` do | consumers must sniff by shape; the client does (`useLiveEmotionStream.ts` `typeof data?.confidence === "number"`) → inconsistent protocol | brittle client branching; a future field named `confidence` breaks dispatch | tag every frame: `{type:"telemetry", …}` |
| **M-02** | `emotion_stream.py:69-125` | inbound `context` mutates only 3 of the many fields the client sends; `elapsed_sec`, `wpm`, `pitch` are server-only | declared-vs-used message surface | silent partial delivery; the client believes it informed the server | one Pydantic model per message type; reject unknown keys in debug |
| **M-03** | `emotion_stream.py` `run_tier2` | `websocket.send_json` sits **outside** the `try/except`, and `hint_active` is set **after** the await | a send failure escapes; concurrent tier-2s can both fire | duplicate/nested hints, unhandled `ConnectionDisconnectedError` | move the send inside the guard; set `hint_active` before awaiting |
| **M-04** | `emotion_stream.py` `finally` | the background tier-2 task is `cancel()`ed but never awaited | clean teardown | a half-sent frame / lingering `to_thread` after close; cancelled work is invisible | `await asyncio.gather(task, return_exceptions=True)` |
| **M-05** | `emotion_stream.py` timing | `elapsed = round(elapsed + chunk_seconds, 2)` charges a fixed 0.1 s per accepted chunk | wall-clock vs assumed-clock | all latencies and `total_silent_seconds` skew on gaps/jitter; Laya stall thresholds (5 s / 10 s) fire early or late | track `time.monotonic()` at decode, or use real sample count |
| **M-06** | `emotion_stream.py` errors | decode/inference exceptions are swallowed with `logger` only; no frame is sent to the client | visible degradation | a stalled HUD that looks like "quiet candidate" | send `{type:"error", stage, retryable}` |
| **M-07** | `services/laya.py:47` `_LAYAS` · `services/emotion.py:_LOCAL_BUFFERS` | process-local dicts, cap 5000 / pop-on-read | shared store | **under any `--workers>1` the REST submit hits another worker → `laya_metrics.available=false` and zeroed `vocal_delivery`, presented as measurements** | move both to Redis (`laya:session:{id}`); refuse multi-worker until then |
| **M-08** | `services/guesstimate/nudge_service.py:61-97` | direct `import httpx` (line 62) and a guarded `from ollama import AsyncClient` (line 79); **`httpx` and `ollama` are both absent from `backend/requirements.txt`** `[V]` | declared deps | works only via transitive installation (openai/chromadb/fastapi pull httpx); the ollama branch silently never runs, so the "ollama model" path is always the httpx fallback | pin `httpx` explicitly; drop the ollama branch or declare it |
| **M-09** | `nudge_service.py:12-13` | `PRIMARY_MODEL = "qwen2.5:1.5b"` and `LLM_TIMEOUT_SECONDS = 1.5` hardcoded; `settings.ollama_model` is only a *fallback* | configurable model | a 1.5 s budget against a locally-hosted model means tier-2 usually degrades to `get_tier1_hint(category)`; the model id is not the one configured anywhere else | read from settings with a default; raise or make the budget per-tier |
| **M-10** | `routes/hr.py` `/answer`, `routes/guesstimate.py` `/submit` | `asyncio.gather(..., return_exceptions=True)` on transcription + emotion | error propagation | a failed transcription becomes a swallowed exception object, and the answer is scored against empty text with HTTP 200 | inspect results; 502 on transcription failure |
| **M-11** | `transcription.py` `transcribe_audio(model_name="small")` vs `config.py:whisper_model_name="base"` | callers pass `"small"` literally; the setting is **referenced nowhere in the codebase** `[V]` | configurable model | dead config; operators changing it change nothing | read `settings.whisper_model_name`; delete the unused key or wire it |
| **M-12** | `models/technical.py:25` | `questions: Mapped[dict]` with `default=list` (the sibling `models/hr.py:25` is `Mapped[list]`) `[V]` | type honesty | annotation contradicts the stored value and every consumer; misleading for `flag_modified` reasoning | change to `Mapped[list]` |
| **M-13** | `database/engine.py:20-22` + live DDL | `PRAGMA foreign_keys → 0`; no `ondelete=` on any FK `[V-live]` | enforced FKs + real cascade | referential integrity is SQLite-config-dependent; on this SQLite host `DELETE /api/sessions/{id}` succeeds via ORM cascade `[V-live]`. **A failure under PostgreSQL once a child row exists is inferred from the shared DDL (`ON DELETE NO ACTION`) and was never demonstrated — `[I]` `[U]`: no PostgreSQL instance was reachable during this audit** | add a `connect` listener enabling FKs; add `ondelete="CASCADE"` to every child FK and re-create the schema |
| **M-14** | `database/engine.py:56-84` `check_and_apply_migrations` | 5 raw `ALTER TABLE ADD COLUMN` calls, two mid-flight commits, entire body inside `except Exception: pass` `[V]` | versioned migrations | half-migrated schema with the error swallowed; added columns can never be `NOT NULL` (→ DB-06 drift) and their `index=True` is silently dropped (→ missing `ix_sessions_round_type`, DB-07) | adopt Alembic with real upgrade/downgrade + index creation |
| **M-15** | `config.py:secret_key` | defaults to `"CHANGE_ME_SET_SECRET_KEY_ENV_VAR_IN_PRODUCTION"`; the comment claims no insecure default; nothing enforces it `[V]` | fail-fast | with C-01 the key is barely consulted, but any deployment that *does* start requiring auth inherits a publicly-known signing secret | raise at import if unset **and** not `DEBUG` |
| **M-16** | `config.py` CORS | hardcoded `localhost:3000`, `localhost:5173`, `127.0.0.1:5173`; **no WebSocket origin check exists** `[V]` | configurable origins + WS origin allow-list | any site in a browser can open the emotion socket (H-02) | move to settings; validate `websocket.headers["origin"]` |
| **M-17** | `main.py` router mounting | `sessions.router` and `analysis.router` are each mounted twice — bare and under `prefix="/api/jam"` → `/api/jam/api/sessions/...` `[V]`, `[V-live]` | one canonical path per operation | 11 duplicate aliases, 60 OpenAPI operations for 49 real handlers; `/api/jam/api/sessions/{id}/feedback` returns **404** because `feedback.router` was *not* re-mounted — an alias set that is incomplete, hence misleading; no frontend uses the prefix | delete the `/api/jam` mounts (or re-mount all four routers consistently and document it) |
| **M-18** | `schemas/session.py` `SessionOut` | serialises `video_path` / `audio_path` — absolute server filesystem paths — in every list and detail response `[V]` | opaque ids / signed URLs | leaks installation layout and real filenames (the same filenames C-04 serves) to every client | remove; expose only `audio_url` |
| **M-19** | `routes/progress.py:631` vs `api/analysis.ts:275` | see **C-11** for the classification decision; the *additional* medium issue is `extended_metrics.mental_math`, which has **no TS interface and no renderer** `[V]` | consumed payloads | dead payload that drifts unnoticed | type it and render it, or delete it server-side |
| **M-20** | `progress.py` verdict bands | 85/70/55 (and `<50` for HR) vs module pages' own bands (`HRReport.tsx:93-99`, `GuesstimateReport.tsx:89-96`, `TechnicalReport.tsx:114-121`, `AnalysisResults.tsx:224,225`) vs backend evaluators; plus calibrated fudges `score*0.95`, `score*0.98`, `rambling = 0.0 if score>=80 else 20.0`, and `float(q["score"]) * 10.0` for Technical `[V]` | one scoring authority | the same session can be "Strong Hire" on one screen and "Developing" on another; the ×10 reveals an unreconciled 1-10 vs 0-100 split | centralise bands + scale in one module (backend `scoring.py`) and expose them via API |
| **M-21** | `routes/{hr,guesstimate,technical}.py` `GET /session/{id}` | inconsistent key sets: Technical omits `created_at` that HR/Guesstimate include; `/start` returns `status` in Guesstimate but `is_complete` in HR/Technical `[V]` | one round-state contract | clients must special-case per module (and do: `GuesstimateStudio` reads neither) | unify into a shared `RoundStateOut` |
| **M-22** | `AnalysisPage.tsx:13-21` | `analyze.isError` / `analyze.error` are never read — only `.isPending` and `.mutate` `[V]` | surface failures | a 500 on `/analyze` leaves the user on the unanalysed session with `status='pending'`, no message, and no re-trigger until remount (`deps=[data?.id, data?.round_type]` + `eslint-disable`) | render `analyze.error`; add an explicit Retry that calls `mutate` |
| **M-23** | `routes/sessions.py:138` and `progress.py` `_user_session_filter` | guest listing hardcodes `user_id == 1` / `user_id == 1 OR IS NULL` `[V]`, `[V-live]` 7 of 19 sessions (37 %) have `user_id NULL` | ownership filter | NULL-owner rows are readable by *any* caller (`_get_session_for_user` skips the check when `session.user_id is None`), and user 1's private history becomes the anonymous public history | backfill `user_id`; make NULL mean "denied"; remove the literal 1 |
| **M-24** | `PlacementReadinessMatrix.tsx:159,183` · `CurriculumCoachCard.tsx:37,65,320-368,425,431` | `card.primary_metric.value` and `card.secondary_metrics.map` unguarded; `activeDay = days.find(…) || days[0]` is `undefined` for an empty `days` array, then `activeDay.status` throws; `d.round_type.toUpperCase()` (`:431`) and `d.title.replace(...)` (`:425`) throw on null `[V]` | defensive rendering of LLM-authored JSON | one malformed coach plan or one null metric takes down the whole dashboard (no error boundary reported in these files) | optional-chain every backend-supplied field; validate the plan JSON server-side against a Pydantic model before persisting |
| **M-25** | `routes/emotion_stream.py:160-235` | the 1 Hz cadence gate (`now - last_inference_time < _INFERENCE_INTERVAL_SEC`) and the 2-second `pcm_window` accumulation are **inside `if is_pcm`**; the `else` (WebM) branch calls `extract_prosody_features(payload)` + `analyze_audio_chunk(payload)` on **every received frame**, each `analyze_audio_chunk` fallback writing a temp `.webm` to disk (`emotion.py:826-832`) | one inference-cost policy for both formats | any frame misclassified out of PCM (→ H-01) pays an unthrottled Parselmouth + wav2vec2 forward pass *plus* per-frame temp-file I/O, and skips windowing so each point covers only 1.5 s instead of a 2 s window. Currently latent: **no client in the repo sends WebM over the socket** `[V]` | hoist the cadence gate and windowing above the branch, or reject non-PCM binary outright per H-01's init-frame fix |

---

# LOW

| ID | File · function | Actual | Discrepancy | Impact | Correction |
|---|---|---|---|---|---|
| **L-01** | `emotion_stream.py` outbound | fields the client computes locally (`wpm`, `pause_rate`) are stripped from the wire while the server also recomputes them `[V]` | two sources for one metric | the HUD and the report can disagree | send one authoritative value |
| **L-02** | `public/audio-processor.js:1-35` *(untracked)* | naive linear-interpolation decimation, no anti-alias filter, `clamped < 0 ? c*0x8000 : c*0x7fff` asymmetric scale `[V]` | resampling quality | aliasing into F0/jitter/shimmer estimates above 8 kHz content | use an `OfflineAudioContext`/`AudioBufferSourceNode` resampler, or a proper polyphase filter |
| **L-03** | `useLiveEmotionStream.ts` | `workletNode.connect(audioCtx.destination)` `[V]` | mic routed to speakers | audible feedback/loopback for the candidate during a recorded round | do not connect to destination (or route only the analyser) |
| **L-04** | `routes/auth.py` `create_access_token` | uses deprecated `datetime.utcnow()` (naive) `[V]` | tz-naive expiry arithmetic | clock-skew-dependent token expiry across DST/timezones | `datetime.now(timezone.utc)` |
| **L-05** | `schemas/user.py` `UserBase.email: str` | `EmailStr` is imported but **unused** `[V]` | declared-but-disabled validation | `register` accepts non-email strings as identity — and identity is the JWT subject lookup, so an odd email permanently shadows that account | annotate with `EmailStr` |
| **L-06** | `api/feedback.ts` `getFeedback` | defined, **zero importers** `[V]` | unused client API | dead contract; drifts silently | delete or wire it |
| **L-07** | `api/technical.ts` `getTechnicalSession(): Promise<any>` `[V]` | unmodelled response | TS cannot catch drift on an endpoint HR/Guesstimate do model | type it |
| **L-08** | `requirements.txt` vs installed venv | pinned `fastapi==0.104.1`, `sqlalchemy==2.0.23`, `numpy>=1.26.2,<2.0.0`, `mediapipe==0.10.13`, `openai-whisper==20231117`; **`from main import app; app.routes` shows only 6 `_IncludedRouter` placeholders** because the venv actually runs **FastAPI 0.147.0** `[V-live]` | pin ≠ environment | lazy router expansion changed observable behaviour and invalidated a naive route-count; `asyncpg` is pinned but **no `create_async_engine` exists anywhere** `[V]` | add a `test_environment_matches_lockfile` check; delete unused pins |
| **L-09** | `main.py` | only `GET /` and `GET /health` are app-level; there is **no `/version`, no `/metrics`, no request-id middleware** `[V]` | operability | no way to correlate a report complaint to a run | add `/version` + a `X-Request-Id` middleware |
| **L-10** | `TechnicalReport.tsx:45-58` | PDF export expands every accordion then `setTimeout(() => window.print(), 150)` `[V]` | timing-dependent render | export truncates on slower machines | await expansion state, or build the PDF server-side |
| **L-11** | `TechnicalReport.tsx:172-178` | `company_tier` 4-way chain ends in `"Early-Stage Seed 0-to-1 Bar"` — matches `COMPANY_TIER_PROFILES` ids today (`evaluator.py:168,183,199,215`) `[V]` | unknown-id fallthrough | a future tier id is silently mislabelled as Early-Stage | default to the raw id + a dev warning |
| **L-12** | `AnalysisResults.tsx:233-243` | the client depends on a `_jam` pseudo-key smuggled inside `session_analyses.filler_words_list` (a filler-word **map** carrying an underscore-prefixed sibling blob) `[V]` | private convention as a contract | an unrelated change to filler storage breaks pace/pause display; `filler_words_list` is `JSON NOT NULL` with no schema | promote `_jam` to a real column or a `report.metrics` entry |

---

# Architecture-level observations (scope G)

`[V]` unless marked.

**A-1 Auth.** One `auth.py`, four resolvers, zero enforcement. The frontend (`App.tsx:69`, `ProtectedRoute` on every route + `AuthContext` bootstrapping `getMe()`) presents a login-gated product whose backend does not check. Duplicated logic: `_get_optional_user` in `sessions.py:67` re-implements the same fallback and is then imported by `progress.py:13` and `coach.py:18` — so a *private helper with a hardcoded `user_id==1`* is the de-facto identity layer for the dashboard and the coach.

**A-2 Session management.** `sessions` is a single universal spine with a `round_type` discriminator plus per-round 1:1 tables — a sound shape — but its two JSON columns are written by five different modules with four live schemas (C-11/H-15), its status is a free string with no state machine (DB-03), and creation ownership is split across five files. JAM additionally creates the row *after* the live telemetry started (C-08).

**A-3 Audio ingestion.** Two entirely separate ingestion models: JAM/rounds upload a `.webm` and analyse it post-hoc; the WS streams raw 16 kHz mono int16 in 3200-byte frames. The PCM contract genuinely matches at both ends `[V-live]` (3200 bytes = 1600 samples = 0.1 s), but it is **established by a modulo heuristic** (H-01) with no negotiation and no init frame. A second, fully-implemented WebM-chunk branch exists on the socket (`_WEBM_CHUNK_SECONDS=1.5`, `emotion_stream.py:207-235`, `analyze_audio_chunk`'s temp-`.webm` decode) — it is **not broken, it is simply unreachable: no client in the repository sends a container frame over the socket** `[V]`. It also bypasses the PCM branch's 1 Hz cadence gate and 2-second windowing (M-25). The terminator verbs `"close"|"stop"|"end"` (`:110`) are in the same category: server-implemented, client-unused (H-03).

**A-4 Acoustic DSP.** **Two independent prosody engines** — `praat-parselmouth` (jitter %, shimmer %, HNR dB, pitch floor 75 / ceiling 500, `dynamic_range_semitones = 12*log2(p95/p5)`) and a numpy/PyAV autocorrelation engine (frame 2048 / hop 512, f0 75-350 Hz, uptalk and terminal-drop detection). They coexist in `services/prosody.py`, are both called from `routes/analysis.py`, and emit different key names — hence the `prosody_confidence 84.0` default sitting next to a MediaPipe eye-contact default in the same dict (C-09).

**A-5 Shared NLP/evaluation.** Four parallel evaluator packages (`services/analysis.py`, `services/hr/evaluator.py`, `services/guesstimate/evaluator.py`, `services/technical/evaluator.py` + `interview_graph.py`) with no shared scoring primitive, no shared `strengths/weaknesses/summary` model, and divergent scales (0-100 vs 1-10). The JAM path uses `services/feedback.py:generate_feedback`; the other three each hand-roll a report generator. **MECE weighting (35/25/20/20) is hardcoded in the guesstimate evaluator.**

**A-6 Feedback generation.** LLM access is **triplicated**: raw `requests.post` to Ollama `/api/generate`, `langchain_openai.ChatOpenAI` against OpenRouter Nemotron with a `langchain_community.ChatOllama` fallback, and `httpx.AsyncClient` to Ollama `/api/chat` in `nudge_service.py` (M-08). Three different timeout regimes (`settings.llm_timeout_seconds=60`, an `asyncio.wait_for(…, 1.5)` in nudges, axios's 120 s). No LLM response is schema-validated — the Pydantic request models (`StartHRRequest`, `CompleteDayRequest`, etc.) validate *inbound client* data only, and **no route declares `response_model` except the legacy `/api/sessions*` family**, so the outbound contract exists solely as whatever dict the handler assembled (H-15, C-11).

**A-7 RAG & memory.** Chroma (`sentence-transformers/all-MiniLM-L6-v2`, `chromadb.HttpClient` on :8100 with a local-persist fallback, collections `user_{id}` and `mem0_memories`) plus Mem0, both reached only from the Technical round and the Coach agent. Cross-store writes are unprotected and best-effort (H-11, H-12). JAM/HR/Guesstimate have no memory at all.

**A-8 Circular / tight coupling.** No import cycles found, but two structural ones: `routes/coach.py` and `routes/progress.py` import a private helper from `routes/sessions.py` (route→route coupling); `routes/technical.py:438` imports `FileResponse` **inside the function body** although it is already imported at module top elsewhere — a symptom of copy-paste growth rather than a defect. `emotion_stream.py` does query the database — `_load_guesstimate_context` (`:37-51`) opens its own `SessionLocal()` and reads `Session.round_type`, `case.category` and `case.question` — but **only to gate the Laya feature; the row's `user_id` is never compared to the caller**, so the DB access buys round-type detection and zero authorization (H-02). `[V]`

**A-9 Placement Readiness Dashboard.** Aggregates four rounds by reading `sessions` + the three detail tables + `round_metadata`, then applies its own thresholds, its own ×10 scale fix for Technical, and its own calibrated fudges (M-20), and hands the result to a consumer whose status union is missing one value (C-11). It is the least-verified surface in the app and the most user-visible.

**A-10 Historical aggregation.** No incremental aggregates, no materialised view, no denormalised daily table. Every dashboard request re-scans `sessions` (whose `round_type` index does not exist — DB-07) plus N detail joins. Acceptable at 19 rows, quadratic in practice, and there is no caching layer anywhere. `[V]`

**A-11 What is *not* live.** The brief assumed a computer-vision service in the real-time path. `[V]` There is none: `FaceTrackingOverlay` / `useFaceTracking` are **browser-local** indicators that never transmit; all CV (`multimodal_tracker.py`) runs post-hoc on the uploaded file. The "avatar reaction" on the report page is a hardcoded dict (C-09), not a rendered avatar. `[V]`

**A-12 Whole real-time pipeline is uncommitted.** `git status` shows the emotion/Laya/WS feature set as pre-existing **uncommitted** work (14 modified files + 2 untracked: `backend/app/services/audio_pcm.py`, `frontend/public/`). `[V]` Several findings above therefore describe code that has never been through review. `[V]`
