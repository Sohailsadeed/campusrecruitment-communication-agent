# SpeakFlow — Per-Module End-to-End Integration Audit

**Audit date:** 2026-10-31 · **Branch:** `feature/hr-round` @ `326d75e` (+14 modified / 2 untracked pre-existing files)
**Mode:** strictly READ-ONLY — no file was created, modified, or deleted besides these audit documents.
**Evidence tags:** `[V]` read from source · `[V-live]` verified by executing code / querying the live DB · `[I]` inferred · `[U]` unknown

Companion documents: `API_CONTRACT_AUDIT.md` (endpoint contracts), `WEBSOCKET_CONTRACT_AUDIT.md` (live stream), `DATABASE_SESSION_AUDIT.md` (persistence), `ARCHITECTURE_RISKS.md` (findings), `AUDIT_SUMMARY.md` (executive view).

---

## 0. Process topology (what actually runs)

```
┌──────────────────────── React 18 + Vite SPA ────────────────────────┐
│  axios (http://localhost:8000, 120s timeout)   native WebSocket      │
│  react-query (sessions/dashboard only)         AudioWorklet PCM      │
└──────────┬──────────────────────────────────────────┬───────────────┘
           │ REST  (49 genuine ops + 11 /api/jam aliases = 60)
           │ WS    (exactly 1 endpoint, 4 outbound event types)
┌──────────▼──────────────────────────────────────────▼───────────────┐
│  ONE FastAPI process  (backend/main.py) — no Java, no microservices │
│  routes/ ── services/ ── agents (LangGraph) ── in-process ML        │
└─┬────────┬──────────┬──────────┬───────────┬───────────┬───────────┘
  │        │          │          │           │           │
 Postgres SQLite    Redis      Ollama     OpenRouter   Chroma
 (fallback→         (emotion/  (qwen2.5   (nemotron-  (user_{id},
  SQLite)            laya)     :1.5b,     3-ultra)     mem0_memories)
                                qwen3.5:4b)
                                 + filesystem upload_dir (webm/wav/pdf)
                                 + HuggingFace hub (wav2vec2-large-robust-12)
```

`[V]` The service layer is **ordinary Python modules imported in-process**, not remote services. There is no HTTP hop between the API and Whisper, the emotion model, MediaPipe, Parselmouth, or LangGraph. Every "AI service" named in the brief is a function call inside the request handler (or, for WS, inside the socket coroutine). `[V]`

**Consequence for every flow below:** the CPU-heavy inference is on the request path, and the sync SQLAlchemy session is held while it runs. `routes/hr.py` and `routes/technical.py` mitigate only *partially*, by wrapping the two slowest calls in `asyncio.to_thread`. `routes/analysis.py` does **not** — it runs Whisper + MediaPipe + Parselmouth + the emotion model + an LLM call **directly inside the request**, blocking the event loop for the entire duration. `[V]`

---

## 1. JAM (60-second impromptu) — topic → record → upload → analyse → report

### 1.1 Happy path, traced `[V]`

```
1  /record  RecordingSession.tsx
     ├─ useMediaRecorder.init() → getUserMedia
     ├─ useFaceTracking(videoRef, active)            → local-only overlay, NOTHING sent to backend
     └─ useLiveEmotionStream(0, isRecording, undefined, recorder.stream)   ← :22  ⚠ session id = 0
2  record start
     ├─ AudioWorklet (public/audio-processor.js): mono → linear-resample 16 kHz → int16
     │     flush at ≥1600 samples → 3200-byte ArrayBuffer → ws.send()
     └─ WS /ws/session/0/emotion  (binary only; no context frame, 3rd arg is undefined)
           backend: is_pcm16_chunk → decode → EMA → buffer_emotion_point(0, …)
                    → laya process_laya_chunk(0, …)      [tier1/tier2 never fire: no question]
3  stop → recorder.videoBlob (webm)
4  POST /api/sessions (multipart)
     form: title, description, duration_seconds, round_type=<paramTrack>, round_metadata{persona,target_wpm}
     file: video_blob  → _save_upload() → upload_dir/<uuid>.webm
     DB: INSERT sessions(user_id, status='pending', video_path, round_metadata)
     ⚠ the ONLY blob uploaded is video — there is no separate audio file, so
       audio_path stays NULL for every JAM row  [V-live: sessions 4-10, audio_path all NULL]
5  POST /api/sessions/{id}/analyze
     status='processing' → commit
     transcribe_audio(video_path, allow_mock=True)     [Faster-Whisper, cpu/int8, word_timestamps, VAD]
     analyze_transcription(text, words)                → pace, fillers, clarity, _jam
     analyze_video(video_path)                         → MediaPipe FaceMesh+Pose
     analyze_audio_prosody(path) + analyze_speech_emotion(path) + extract_prosody_features(path)
     generate_feedback(...)                            → LLM (Ollama qwen3.5:4b / OpenRouter)
     DB: INSERT transcriptions, session_analyses, ai_feedback
         UPDATE sessions SET overall_score, round_metadata, report, status='completed' → commit
6  navigate /analysis/:id → AnalysisPage → useSessionDetail + AnalysisResults
```

### 1.2 Where this flow diverges from what the module is supposed to do

| # | Divergence | Evidence | Severity |
|---|---|---|---|
| J-1 | **Live telemetry is generated against session `0` and never read.** The row is created at step 4 with a real id; nothing migrates `emotion:session:0`. Redis `EXPIRE 3600` deletes it. JAM is the only round whose vocal-delivery HUD is decorative. | `RecordingSession.tsx:22` `[V]`, `emotion.py:471-472` `[V]`, grep: `analysis.py` never calls `get_session_emotion_summary` `[V]` | **CRITICAL** |
| J-2 | **`/api/jam` prefix is a trap.** `sessions.router` and `analysis.router` are re-mounted under `/api/jam` (`main.py`), producing `/api/jam/api/sessions/...` (note the doubled `/api`). `feedback.router` is **not** re-mounted, so `/api/jam/api/sessions/{id}/feedback` → **404**, live-confirmed. No frontend file uses the prefix. | `main.py:…` `[V]`, `[V-live]` TestClient probes | HIGH |
| J-3 | **Two independent JAM creation paths with different lifecycles.** `POST /api/sessions` (multipart, `pending`) vs `POST /api/sessions/json` (client-supplied `overall_score` **and** `report`, immediately `completed`). Sessions 14/15/19 are the latter: `completed`, no transcription, no feedback, no media, `round_metadata={'mode':…}`. | `[V]` routes, `[V-live]` DB | HIGH |
| J-4 | **The JAM report schema is not fixed.** Live rows carry three different key sets (6 → 7 → 9/10) under `round_type='jam'`. `AnalysisResults.tsx` compensates with `||` fallbacks for every section (`:132` competencies, `:164-173` rewrites, `:197` sparkline, `:212-221` drills). | `[V-live]` §3.1 of DATABASE_SESSION_AUDIT | HIGH |
| J-5 | **Fabricated nonverbal data.** When MediaPipe/OpenCV/video are unavailable, `multimodal_tracker._deterministic_fallback` returns `rng.uniform(76,92)` eye contact and `rng.uniform(80,94)` posture from `random.Random(hash(video_path))`, i.e. a *reproducible but entirely invented* score, plus `hand_gestures_count randint(2,6)` / `fidget_count randint(0,2)`. On the exception path of `/analyze`, `analysis.py` hardcodes `eye_contact_percentage 82.0`, `posture_quality 85.0`, `prosody_confidence 84.0`, `vocal_energy_db -22.0`, `tone_verdict "Measured & Structured"`, and a whole `avatar_reaction` object. | `[V]` both files | **CRITICAL** (latent: `mediapipe 0.10.13` installed, so it does not fire today `[V-live]`) |
| J-6 | **Fabricated transcripts.** `transcribe_audio(..., allow_mock=True)` returns a canned `MOCK_TRANSCRIPTS` paragraph with `confidence: 0.88` and synthetic pauses when both Whisper backends fail. JAM's `/analyze` path is the one that passes `allow_mock` truthy. | `[V]` `transcription.py` | **CRITICAL** (latent: `faster_whisper 1.2.1` installed `[V-live]`) |
| J-7 | **No audio is uploaded separately**, so every audio-only analysis (`analyze_audio_prosody`, `analyze_speech_emotion`) re-decodes the `.webm` via PyAV. `session_media.get_session_audio_path` therefore falls back to `video_path` — correct, but it means the "audio" playback on the report page is a video container served as `audio/webm`. | `[V]` | LOW |
| J-8 | `create_session` is `async def` yet performs blocking `while chunk := file.file.read(256KB)` on `UploadFile.file` — the event loop stalls during a 200 MB upload, freezing the WS telemetry of every other live session. | `[V]` `routes/sessions.py` | HIGH |
| J-9 | The JAM analysis endpoint has **no auth dependency at all** — `POST /api/sessions/{id}/analyze` takes only `session_id`, `db`. Any client that can reach the port can trigger (and overwrite) analysis on any session id. | `[V]` | **CRITICAL** |

### 1.3 JAM client-side re-computation

`AnalysisResults.tsx` derives, without any backend field: `Math.round((pace/60)*durationSec)` as a *word count* (`:129`); six competency scores from `score`/`pace`/`fillersCount` (`:132-139`); percentile claims `"Top 8th/20th/40th Percentile"` (`:225`); verdict bands at 82/70 (`:224`). `[V]` The backend's `report.competencies` exists, so this is a **fallback that silently substitutes invented telemetry** whenever the report is missing or old-shaped — which, per `[V-live]`, is the case for sessions 4, 5, 14, 15, 19.

---

## 2. HR Behavioral — question delivery → answer → STAR eval → report

### 2.1 Flow `[V]`

```
/hr  HRStudio.tsx
 ├─ GET /api/hr/tracks                → {tracks:[{id,label,description}]}   (unauthenticated? no — get_current_user)
 ├─ POST /api/hr/start  {role, target_company?, interview_mode='standard_hr', max_questions(1..8)=4}
 │     DB: INSERT sessions(round_type='hr', status='in_progress', round_metadata={})
 │         INSERT hr_interviews(role, target_company, interview_mode, max_questions,
 │                              question_count=0|1, questions=[…], current_question={…})
 │     → {session_id, current_question, question_count, max_questions, is_complete}
 ├─ useLiveEmotionStream(sessionId, isRecording)      ← :60  NO context object
 │     ⇒ question_text stays None ⇒ tier-2 Laya path is inert for HR
 ├─ per question: TTS question via GET /api/hr/.../tts? / window.speechSynthesis (client)
 │     answer: Web Speech API transcript OR typed text; MediaRecorder webm (optional)
 ├─ POST /api/hr/answer   multipart Form: session_id:int, answer:str, audio_file:File?
 │     await audio_file.read()      ← unbounded, no size check on this path
 │     asyncio.gather(to_thread(transcribe_audio(dest,'small',False)),
 │                    to_thread(analyze_speech_emotion(dest)), return_exceptions=True)
 │     evaluate_hr_answer(...)      → LLM → {star:{completeness_score, situation/task/action/result
 │                                       {present,summary}, structure_critique},
 │                                    personal_ownership_score/ownership_critique,
 │                                    specificity_score/…, relevance_score/…,
 │                                    ideal_star_script, coaching_feedback, overall_score}
 │     hr.questions = list(hr.questions)+[answered]   ⚠ read-modify-write, no lock
 │     hr.question_count = len(hr.questions)
 │     if question_count >= max_questions: generate_hr_report(...) → sessions.report,
 │                                          sessions.overall_score, status='completed'
 │                                          + get_session_emotion_summary(session.id) [DRAINS Redis]
 │     → {is_complete, report?, next_question?, question_count, evaluation, audio_url, vocal_delivery}
 └─ /hr/report/:id → GET /api/hr/report/{id} → {questions, report, overall_score, role,
                        target_company, interview_mode, created_at}
```

### 2.2 Verified integration defects

| # | Divergence | Evidence | Sev |
|---|---|---|---|
| H-1 | **The per-question evaluation is thrown away.** `HRStudio.tsx:243-256` reads only `is_complete, report, next_question, question_count` — never `evaluation`. The candidate gets no feedback between questions; the only place it surfaces is `/report`, which re-reads it out of the JSON column. | `[V]` page trace | MEDIUM |
| H-2 | **Missing `else` on the answer reply.** `if (is_complete && report) … else if (next_question) …` with no terminal branch (`:245-256`). A reply with `is_complete=false, next_question=null` is a **silent no-op**: the UI keeps showing the same question while `hr.question_count` has already advanced server-side → the same question can be re-submitted, double-counting into `questions`. | `[V]` both sides | HIGH |
| H-3 | **Audio is almost never uploaded in HR.** `mediaRecorderRef.stop()` (`:230`) and `submitHRAnswer(..., recordedAudioBlob)` (`:243`) are in the same synchronous block; `recordedAudioBlob` is only set by the asynchronous `recorder.onstop` (`:169-173`). So submitting *while recording* posts `null` audio — and the blob that arrives during the `await` is then cleared at `:252` or orphaned by navigation. | `[V]` ordering; `[I]` browser timing | HIGH |
| H-4 | **No `context` frame for HR** (`:60`, third arg omitted). Backend `emotion_stream` only sets `question_text`/`is_guesstimate` from `context['question']`; tier-2 Socratic nudges therefore cannot fire on HR even though the socket is open. `LiveCoachNudge` is not imported by HRStudio at all. | `[V]` | MEDIUM |
| H-5 | **`interview_mode` is not a validated enum.** `get_initial_hr_question(track='standard_hr')` and `track='totally_bogus'` both return an arbitrary question — live-probed. `[V-live]` There is no server-side whitelist matching the `HRStudio.tsx:31` default or the `:430-435` selector ids. `HRReport.tsx:150` then `.replace('_',' ')` on it unguarded. | `[V-live]` `[V]` | MEDIUM |
| H-6 | **`q.track` is optional server-side, required client-side.** `hr.py:173` uses `curr_q.get("track", …)`; `HRReport.tsx:304,323` calls `q.track.replace(...)` unguarded → a null-track row throws the whole report page. | `[V]` `[I]` for the throw condition | MEDIUM |
| H-7 | **`reportSummary.strengths.map` / `.weaknesses.map` unguarded** (`:659`, `:675`) inside only `{reportSummary && …}`. `generate_hr_report` always emits both lists — but a session whose `report` was written by *another* path (see J-3, DB-05) has neither key. `[V]` | `[V]` | MEDIUM |
| H-8 | **Lost-update race on `hr.questions`** (see DB-01). No lock, no `flag_modified`, no version. | `[V]` | **CRITICAL** |
| H-9 | `db.get(SessionModel, session_id)` with `current_user` resolved but **never used to authorise** the write. Any authenticated user can post answers into another user's HR session by guessing the id. | `[V]` `routes/hr.py` | **CRITICAL** |
| H-10 | `await audio_file.read()` loads the entire upload into memory with no size cap (contrast `_save_upload` in `sessions.py`, which enforces `max_upload_size_mb`). | `[V]` | HIGH |
| H-11 | **Verdict bands duplicated client-side only** — `HRReport.tsx:93-99` uses ≥85 / ≥70 / <50; the backend `evaluator.py:325` emits a bare int `total_score`. `progress.py` uses its own 85/70/55 bands (and `<50` for HR). Three band tables, none shared. | `[V]` | MEDIUM |
| H-12 | Reload mid-interview restores the server question (`:80-83`) but **discards the drafted answer and recorded blob** (component state only). The restore failure path (`:90-93`) silently `removeItem` + `setSessionId(null)`, dropping the user back to setup with no message — the in-flight interview becomes unreachable. | `[V]` | MEDIUM |

---

## 3. Guesstimate / Market Sizing — and the Laya coaching loop

This is the only module where **all three feedback channels are wired end-to-end**, and the only page that passes `context` to the socket. `[V]`

### 3.1 Flow `[V]`

```
/guesstimate  GuesstimateStudio.tsx
 ├─ GET /api/guesstimate/metadata      (NO auth dependency) → categories, difficulties, approaches
 ├─ GET /api/guesstimate/random?category=&difficulty=   (NO auth) → {question}   [preview shuffle]
 ├─ POST /api/guesstimate/start {category, difficulty, question, approach_type}
 │     DB: INSERT sessions(round_type='guesstimate', status='in_progress', round_metadata={})
 │         INSERT guesstimate_cases(question, category, difficulty, approach_type)
 │     → {session_id, question, status}      ⚠ key is `status`, NOT `is_complete`
 ├─ useLiveEmotionStream(sessionId, isRecording,
 │       { category, question: activeQuestion, partialTranscript: answerText })   ← :103-107
 │       hook sends {type:'context', category, question, partialTranscript}
 │       backend reads context['question'] / context['category']  (snake_case!)
 │       backend reads context['partial_transcript']              → ⚠ MISMATCH, always None
 ├─ LIVE LOOP (WS, per 3200-byte frame)
 │     decode → RMS(0.015) → Laya cadence history → tier gates
 │       tier1 (stall ≥5s, dedup tier1_fired)  → {type:'coach_nudge', tier:1, message: get_tier1_hint(category)}
 │       tier2 (stall ≥10s, dedup tier2_fired) → generate_tier2_nudge(question, partial_transcript, category)
 │            models: ['qwen2.5:1.5b', settings.ollama_model] , 1.5s asyncio.wait_for each
 │            → _generate_with_model: try `from ollama import AsyncClient`
 │                 ImportError → _generate_with_httpx POST {ollama}/api/chat
 │            all fail → get_tier1_hint(category)      ← never returns null
 │       recovery → {type:'clear_nudge'}
 │     1 Hz inference → telemetry frame (NO 'type' key) {arousal,valence,dominance,
 │            confidence,nervousness,composure,pitch_mean_hz,delivery_style,elapsed_sec,…}
 │     buffer_emotion_point(session_id, point) → Redis RPUSH + EXPIRE 3600
 ├─ POST /api/guesstimate/submit (multipart Form session_id, answer, …, audio_file?)
 │     transcribe + analyze_speech_emotion + evaluate_guesstimate (LLM, MECE 35/25/20/20)
 │     eval_result['vocal_delivery'] = get_session_emotion_summary(session.id, fallback=vocal_delivery)  ← DRAINS Redis
 │     eval_result['laya_metrics']   = get_session_laya_metrics(session.id)                              ← DRAINS _LAYAS
 │     DB: guesstimate_cases.evaluation = eval_result ; sessions.report = eval_result ;
 │         sessions.overall_score ; status='completed'
 │     → {session_id, overall_score, evaluation, audio_url, vocal_delivery}
 │        ⚠ client reads ONLY res.session_id (:318) — the whole evaluation is discarded
 └─ /guesstimate/report/:id → GET /api/guesstimate/report/{id}
```

### 3.2 The Laya loop — what is real and what is not

`[V]` `services/laya.py` keeps state in a **process-local dict** `_LAYAS: Dict[int, LayaSessionState]` (`:47`) — no Redis, no DB. `get_session_laya_metrics(session_id, cleanup=True)` (`:160`) pops it. Therefore:

| Aspect | Verified status |
|---|---|
| Tier-1 hints | **real and wired.** `get_tier1_hint(category)` from `CATEGORY_SCAFFOLDS` (`:19-27`); dedup via `tier1_fired`; reaches UI via `LiveCoachNudge` (mounted only by `GuesstimateStudio.tsx:773`). |
| Tier-2 Socratic hints | **plumbed but crippled by two independent defects.** (a) `partial_transcript` is never received — the client sends `partialTranscript` (`useLiveEmotionStream.ts:291-297`) and the server reads `context['partial_transcript']` (`emotion_stream.py`). `[V]` both ends. So the prompt's evidence half is always empty. (b) It requires `question_text`, which only arrives via `context['question']` — that *does* work for Guesstimate (`:103-107` passes `question:`). So tier-2 fires, but always against `partial_transcript=''`. |
| Metrics | `rebound_agility_score, cadence_stability, hints_issued, rebound_success_count, average_rebound_latency_sec, speech_ratio, total_speech_seconds, total_silent_seconds, available` `[V]` — all surface in `evaluation.laya_metrics` and are rendered at `GuesstimateReport.tsx:246,273`. |
| Multi-worker safety | ✗ **broken by construction.** `_LAYAS` and `_LOCAL_BUFFERS` are per-process. Under any `--workers > 1` deployment the REST submit hits a different worker than the WS and receives `{'available': False, …all zeros}`. Same for the Redis-less emotion fallback. `[V]` |
| Persistence | ✗ nothing in the DB. If the user never submits, hints/cadence are unrecoverable. `[V]` (DB-09) |

### 3.3 Verified defects

| # | Divergence | Evidence | Sev |
|---|---|---|---|
| G-1 | **`partialTranscript` vs `partial_transcript`** — the Socratic prompt's only evidence input is always empty. | `[V]` both ends | **CRITICAL** (functionally, for this module) |
| G-2 | **`/start` returns `status`, `/submit` and `/session` return `is_complete`** — two different completion keys on one module. `GuesstimateStudio.tsx` reads neither from `/start`. | `[V]` `guesstimate.py:102-108` | MEDIUM |
| G-3 | **Restore effect has no `!activeQuestion` guard** (deps `[sessionId, navigate]`, `:130-161`). `handleStartDrill` sets `setSessionId(res.session_id)` (`:275`) → the effect re-fires → a "Restoring" flash (`:333+`) and a **redundant `GET /session/{id}`** immediately after `/start`, then `setCategory(data.category)` (`:142`) overwrites the just-submitted UI state. Contrast HR `:72` and Technical `:126`, which both guard. | `[V]` | MEDIUM |
| G-4 | **Submit failure leaves the round server-side finished.** `candidate_answer` (`:182`) and `status='completed'` (`:188`) persist before the response returns; a client-side error keeps `answerText` and shows no indication the round is over → re-submit re-evaluates the same session and re-drains an already-empty Redis buffer (`vocal_delivery` then silently becomes the `fallback=` value). | `[V]` `[I]` re-submit effect ordering | HIGH |
| G-5 | **`mece_score ?? 75`, `assumption_score ?? 75`, `mental_math_score ?? 75`, `sanity_check_score ?? 70`** rendered as real `/100` telemetry when the backend omits them (`:334-382`). Four fabricated sub-scores on the report the user acts on. | `[V]` | HIGH |
| G-6 | `rangeDiag?.status` is switched only for `"within_range"`/`"below_range"` (`:420-427`); any other backend status renders as a neutral grey chip carrying `summary_label` text — i.e. a *warning presented as neutral*. | `[V]` `[U]` full backend enum surface | MEDIUM |
| G-7 | **The entire `/submit` evaluation payload is discarded** (`:311-318` reads only `session_id`) and then re-fetched from `/report`. One extra round trip of a ~40-key JSON body. | `[V]` | LOW |
| G-8 | Same MediaRecorder race as H-3 (`:298` stop, `:311-316` read pre-stop blob). | `[V]` | HIGH |
| G-9 | **`GET /random` and `GET /metadata` are the only unauthenticated read endpoints in the app** (`guesstimate.py`) while every other router resolves a user. | `[V]` | LOW (they expose only canned questions) |
| G-10 | `eval_result` written to **both** `guesstimate_cases.evaluation` and `sessions.report` → two copies of a 40-key blob that can diverge. | `[V]` (DB-13) | MEDIUM |
| G-11 | The whole `laya_metrics` object is `available: False` + zeros if the WS never opened (e.g. `isRecording` false, or a different worker). `GuesstimateReport.tsx:246` then calls `.toFixed(1)` on `average_rebound_latency_sec` and `Math.round(speech_ratio*100)` — valid JSON numbers, so no throw, but a **0.0 s latency / 0 % speech ratio displayed as measured facts** rather than "no data". | `[V]` `[I]` user misreading | MEDIUM |

---

## 4. Technical round — resume RAG + LangGraph interview

### 4.1 Flow `[V]`

```
/technical  TechnicalStudio.tsx
 ├─ GET /api/technical/resume/status → {has_resume, resume_name}
 ├─ POST /api/technical/resume/upload (multipart PDF)
 │     process_resume(pdf) → PyPDFLoader → RecursiveCharacterTextSplitter(500/50)
 │       → Chroma collection user_{id} (HttpClient :8100, else local persist)
 │     DB: users.resume_path, resume_name ; db.commit()
 │     ⚠ except Exception: logger.warning  → STILL RETURNS SUCCESS
 ├─ POST /api/technical/start {role, target_company, company_tier, max_questions}
 │     DB: INSERT sessions(round_type='technical', status='in_progress', round_metadata={role,target_company})
 │         INSERT technical_interviews(role, target_company, resume_context, max_questions,
 │                                     question_count, questions=[q1], current_question)
 │     → {session_id, current_question, question_count, max_questions, is_complete,
 │         role, target_company, company_tier}   ⚠ client reads only session_id + current_question
 ├─ useLiveEmotionStream(sessionId, isRecording)   ← :99  NO context, NO nudge component
 ├─ POST /api/technical/answer {session_id, answer, audio_file?}
 │     interview_graph.invoke(state)     LangGraph, NO checkpointer →
 │        state rebuilt from technical_interviews.questions on EVERY HTTP request
 │        retrieve_context (Chroma) + get_user_history (Mem0) feed the prompt
 │     fallback: graph_res.get("evaluation") or {"score": 7, "feedback": "Good response."}
 │     tech.questions = [...]; tech.question_count += 1        ⚠ same lost-update race as HR
 │     on last: evaluator report → sessions.report / overall_score / status='completed'
 │              + get_session_emotion_summary(session.id)
 └─ /technical/report/:id → GET /api/technical/report/{id}
```

### 4.2 Verified defects

| # | Divergence | Evidence | Sev |
|---|---|---|---|
| T-1 | **`resume/upload` reports success after a swallowed failure.** `process_resume` is wrapped in `except Exception: logger.warning`, and the endpoint returns the OK payload regardless. The user sees "Resume linked"; the Chroma collection may contain nothing, so every subsequent `retrieve_context` returns empty and the interview is generic. | `[V]` `routes/technical.py` | **CRITICAL** |
| T-2 | **`GET /api/technical/audio/{filename}` has no auth dependency at all** — the only such endpoint in the app (HR's equivalent requires auth). Combined with a filename taken from the URL, it is the most direct file-exposure surface. | `[V]` | **CRITICAL** |
| T-3 | **Audio is never uploaded in Technical.** `handleSubmitAnswer` stops only the speech recogniser (`:321-324`) and never calls `mediaRecorderRef.current.stop()`; `recordedAudio_blob` is produced solely by `recorder.onstop` (`:214-218`) and is nulled on every record start (`:201`). So per-question `audio_url` / `vocal_delivery` are systematically absent unless the user manually toggles recording off first. | `[V]` client; `[V]` `technical.py:337-339` only stamps what it receives | HIGH |
| T-4 | **`max_questions` is never synced from the server.** Restore (`:135-141`) reads `question_count` but not `max_questions`, so after reload `maxQuestions` reverts to the local default `5` (`:67`). The header `Question {n+1} of {max}` (`:797`) and the button label `questionCount+1 >= maxQuestions ? "Complete & View Report" : "Next Question"` (`:892`) — which mirrors the server completion rule — are both then wrong. Combined with the missing-`else` bug (identical to H-2, `:336-348`), a 3-question plan shows "Next Question" after the round is already complete server-side. | `[V]` both sides | HIGH |
| T-5 | **Scale split: per-question 0-10 vs report 0-100.** `TechnicalReport.tsx:396,452` renders `q.score` as `/10`; `:260,287` render `avg_conciseness_score`/`avg_understanding_score` as `/100` — from the same dossier. Fabricated fallbacks: `q.conciseness_score ?? 8`, `?? 80`, `?? 82`, and `q.score !== undefined ? q.score : 0` (0 shown as a real score, not "n/a"). | `[V]` `[I]` for the graph's scale provenance | HIGH |
| T-6 | **Two report shapes, one reader.** `[V-live]` sessions 11/13 carry `{summary, strengths, weaknesses, total_score}`; 16/20 carry `{executive_summary, avg_*, rambling_rate_percent, total_score}`. The page reads `.summary` (`:111`) → the *current* shape's summary is never shown. `progress.py` multiplies `float(q["score"]) * 10.0` to reconcile the 1-10 scale — a third place the scale is handled. | `[V-live]` `[V]` | **CRITICAL** (contract) |
| T-7 | **`DELETE /api/technical/resume` nulls the DB columns but never deletes the Chroma collection**; `store_performance` (Mem0) is called **after** `db.commit()`. Re-uploading the same PDF accumulates duplicate chunks; a Mem0 failure leaves the DB claiming a resume exists. | `[V]` (DB-10, DB-11) | HIGH |
| T-8 | **No LangGraph checkpointer.** `[V]` `interview_graph` is invoked per HTTP request with state reconstructed from the JSON column — so the graph is stateless-by-rebuild, and every conversation-history-dependent prompt is only as good as that reconstruction. No graph state is ever persisted. | `[V]` | MEDIUM |
| T-9 | **Hardcoded LLM fallback `{"score": 7, "feedback": "Good response."}`** when the graph yields no `evaluation` — a 7/10 presented as a graded answer. | `[V]` | HIGH |
| T-10 | `GET /api/technical/session/{id}` omits `created_at` while HR and Guesstimate equivalents include it; `TechnicalStudio` does not read it, but `TechnicalReport.tsx:160-185` does read `created_at` from `/report`. Inconsistent key sets across three near-identical endpoints. | `[V]` | MEDIUM |
| T-11 | `toggleRecording` on a browser without SpeechRecognition `alert()`s and returns (`:229-231`) **without stopping** the already-acquired `getUserMedia` stream/recorder (`:207-220`) → the mic indicator stays live while the UI claims the feature is unavailable. Also `{mimeType:'audio/webm'}` is set with no `MediaRecorder.isTypeSupported` check (`:208`); the throw lands in a `console.warn` catch (`:221-223`) while `isRecording` is already true (`:228`). | `[V]` | MEDIUM |
| T-12 | Timer effect gated on `if (sessionId)` only (`:159-165`) — missing the `!isRestoring` guard Guesstimate uses (`:166`), so `elapsedSeconds` accumulates during the blocking restore fetch and during the "Restoring…" branch (`:365-371`). | `[V]` | LOW |
| T-13 | Field-name divergence for the same concept: HR uses `evaluation.star_structure.*.{present,summary}` + `structure_critique`; Technical uses `q.star_breakdown.{situation,task,action,result}` (truthiness only) + `structure_feedback`. Two schemas, two pages, no shared type. | `[V]` | MEDIUM |
| T-14 | `company_tier` fallthrough: `TechnicalReport.tsx:172-178` ends its 4-way chain with `: "Early-Stage Seed 0-to-1 Bar"`, so **any unknown tier id is labelled Early-Stage Seed**. Matches `COMPANY_TIER_PROFILES` ids today. | `[V]` `[I]` for future ids | LOW |

---

## 5. Cross-module: coach agent, dashboard, and the placement readiness rollup

```
DashboardPage
 ├─ GET /api/progress/summary            → weekly/daily series, weakest/strongest
 ├─ GET /api/progress/placement-readiness→ {cards[4], ready_count, attempted_count,
 │                                          total_rounds, evaluation_rule}
 │     each card {key,status,attempt_count,track_number,title,
 │                primary_metric{value,label,unit}, secondary_metrics[], report_path, drill_path}
 └─ CurriculumCoachCard (fetches by itself, NOT via react-query)
       GET  /api/coach/active      → {has_plan, plan{target_role, days[]}}
       POST /api/coach/generate    → {plan}                  (LangGraph curriculum_agent)
       POST /api/coach/complete    → {success}               ⚠ CompleteDayRequest.notes dropped
       POST /api/coach/auto-sync   → {synced, completed_day, score_achieved, message}
```

### 5.1 Verified defects

| # | Divergence | Evidence | Sev |
|---|---|---|---|
| P-1 | **`"developing"` is emitted but unrepresentable.** `progress.py:631` can return `status: "developing"` for the guesstimate card; `api/analysis.ts:275` types the union as `"ready"｜"in_progress"｜"not_attempted"`; `PlacementReadinessMatrix.tsx:30-52` switches on those three with `default: → label "Unattempted"`. A *started* guesstimate round therefore renders as **"Unattempted"** with the `radio_button_unchecked` icon and the dimmed `opacity-90` card class (`:119-124`) — and TypeScript cannot catch it because the value arrives as JSON at runtime. Ironically the switch already uses the string "Developing" as the label for `in_progress` (`:40`). | `[V]` all three files | **CRITICAL** (highest-visibility user-facing contract break) |
| P-2 | **`card.primary_metric.value` dereferenced without optional chaining** (`:159`), guarded only by `hasAttempts &&`; `card.secondary_metrics.map` (`:183`) likewise unguarded. An attempted card with a null metric throws the whole matrix. | `[V]` `[U]` whether the backend can emit that shape | HIGH |
| P-3 | **Backend-supplied route strings are navigated verbatim**: `card.report_path` (`:204`), `card.drill_path` (`:212`), `activeDay.drill_route` (`CurriculumCoachCard.tsx:363-368`) — the last is also *printed* in visible text. A malformed `drill_route` from the LLM planner becomes a broken in-app navigation with no validation layer. | `[V]` | MEDIUM |
| P-4 | **`extended_metrics.mental_math`** is emitted by `progress.py` and has **no TypeScript interface and no renderer**. Verified-unused payload. | `[V]` | LOW |
| P-5 | `getRoundBadge(round: string)` (`:112-124`) has `case "hr": default:` → **every unknown or null round type is labelled "HR Leadership"**. Takes `string`, not `RoundType`, so TS cannot flag a new backend round. | `[V]` | MEDIUM |
| P-6 | `d.round_type.toUpperCase()` (`:431`) and `d.title.replace(...)` (`:425`) unguarded; `activeDay = days.find(…) || days[0]` (`:37,65`) is `undefined` for an empty `days` array, after which `activeDay.status` (`:320-368`) throws. Coach plan JSON is LLM-authored, so emptiness is reachable. | `[V]` `[U]` whether the planner can emit `days: []` | HIGH |
| P-7 | **Every coach failure path is `console.error` only** (`:45,71,88,104`) — a 500 on generate/complete produces no user-visible change; `syncMessage` (`:27`) is set only by auto-sync. `completeCurriculumDay` reads only `res.success` and **never re-fetches the plan**, so the card shows stale day status after a completion. | `[V]` | MEDIUM |
| P-8 | **`CompleteDayRequest.notes` is accepted and silently discarded.** | `[V]` `routes/coach.py` | MEDIUM |
| P-9 | **Magic-number authorization hole**: `coach.py` `if not plan or (plan.user_id and plan.user_id != user_id and user_id != 1)` — user 1 bypasses every ownership check; a plan with `user_id IS NULL` is readable by anyone. `_resolve_user_id(None) → 1` compounds it. | `[V]` | **CRITICAL** |
| P-10 | **`/api/coach/auto-sync` matches `days[].round_type` to the user's latest session and auto-completes it** — an endpoint that mutates curriculum state from session history with no confirmation and no idempotency key. It is user-triggered (`CurriculumCoachCard.tsx:235` `onClick={handleAutoSync}`), and unlike `complete` it *does* re-fetch the plan (`:100`), so the two completion paths behave differently. Repeated clicks on the same day re-match the same "latest session". | `[V]` both sides | MEDIUM |
| P-11 | **Three verdict-band tables** (module pages, `progress.py`, backend evaluators) and **three score scales** (0-100, 0-10 ×10, 0-1) coexist with no shared authority. `progress.py` additionally applies calibrated multipliers `score*0.95`, `score*0.98` and `rambling = 0.0 if score>=80 else 20.0`. | `[V]` | HIGH |

---

## 6. Module integration health (evidence-based)

| Module | Live WS `context` | Nudge UI | Redis telemetry consumed | Audio actually uploaded | Report shape stable | Ownership enforced | Client terminal-state handled | Verdict |
|---|---|---|---|---|---|---|---|---|
| **JAM** | ✗ (id `0`) | ✗ | ✗ **written, never read** | ✓ (video container) | ✗ 3 shapes | ✗ `/analyze` unauth | ~ (has a `failed` branch) | **UNHEALTHY** |
| **HR** | ✗ (no ctx) | ✗ | ✓ `/answer` drains | ✗ race H-3 | ✓ 1 shape | ✗ no authz check | ✗ missing `else` | **AT RISK** |
| **Guesstimate** | ✓ (only module) | ✓ tier1/tier2 | ✓ `/submit` drains | ✗ race G-8 | ✓ 1 shape (×2 copies) | ✗ no authz check | ~ single-shot, but G-4 | **PARTIALLY HEALTHY** — the best-integrated module, and even here `partial_transcript` is broken |
| **Technical** | ✓ socket, ✗ no ctx | ✗ | ✓ `/answer` drains | ✗ **never** (T-3) | ✗ 2 shapes | ✗ `/audio` fully open | ✗ missing `else` | **UNHEALTHY** |
| **Coach / Dashboard** | n/a | n/a | n/a | n/a | LLM-authored JSON | ✗ user-1 bypass | ✗ console-only errors | **AT RISK** |

**No module is fully healthy.** Guesstimate is the closest — it is the only place the real-time coaching loop actually reaches a human, and its defect there (G-1) is a one-key naming mismatch, which is itself the strongest evidence that the WS contract was never written down. `[V]`
