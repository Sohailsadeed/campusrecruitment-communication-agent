# SpeakFlow — Audit Summary

**Audit:** API Contract & Architecture Integration Audit · **Date:** 2026-10-31
**Target:** `C:\Users\Sohail\Cadra Project\speakflow` · branch `feature/hr-round` @ `326d75e`, with **14 pre-existing modified files + 2 untracked paths** (`backend/app/services/audio_pcm.py`, `frontend/public/`) that were in the tree before this audit began. `[V]`
**Constraint honoured:** strictly READ-ONLY. No source file was created, modified, refactored, or deleted. The only writes performed were these six documents under `docs/audits/`. One probe row created during live endpoint testing (session 23) was deleted again; `git status` was re-checked and is unchanged from its pre-audit state. `[V]`

---

## 1. Three premises in the brief that the code does not support

These are stated first because they change what "integration audit" means here. `[V]`

| The brief assumed | The codebase actually contains |
|---|---|
| A Java tier alongside Python | **No Java anywhere.** One single-process FastAPI app (`backend/main.py`). |
| A Python AI **microservice** tier called over HTTP | `backend/app/services/*` are **ordinary in-process Python modules**. Whisper, the audEERING wav2vec2 model, MediaPipe, Parselmouth and LangGraph are function calls inside the request handler — there is no network hop and therefore no service contract to audit there. |
| Computer vision in the real-time path; Pydantic contracts "or equivalent" | CV runs **post-hoc** on the uploaded file only. The browser's `useFaceTracking`/`FaceTrackingOverlay` never transmit. **No route declares `response_model` except the legacy `/api/sessions*` family** — every module route is annotated `-> dict` and returns a hand-built dict, and no LLM output is schema-validated. |

---

## 2. Communication surface, counted

Counts were obtained by **executing the application**, not by counting decorators — `from main import app; app.openapi()` — because the installed FastAPI (0.147.0) differs from the pin (0.104.1) and expands mounted routers lazily, which makes a naive `app.routes` walk report only 6 entries. `[V-live]`

| Metric | Count |
|---|---|
| REST route decorators | **49** genuine operations (47 across 10 routers + 2 app-level: `GET /`, `GET /health`) |
| Duplicate `/api/jam` alias operations | **11** (`/api/jam/api/sessions/…` — sessions + analysis routers re-mounted) |
| **Total OpenAPI operations** | **60** |
| **Total distinct paths** | **54** |
| WebSocket endpoints | **1** — `/ws/session/{session_id}/emotion` |
| **Total communication contracts** | **61** |
| WebSocket **outbound** event types | **4** — telemetry (carries **no `type` key**), `coach_nudge` tier 1, `coach_nudge` tier 2, `clear_nudge` |
| WebSocket **inbound** message classes | **2** — binary audio frames; text frames (`{type:"context",…}` **or** the raw verbs `"close"｜"stop"｜"end"`) |
| ORM tables | **10** · relationships: 1×`users→sessions` 1:N, 5× `sessions→*` 1:1, 1× 1:N `ai_feedback`, 1× `users→curriculum_plans` 1:N, 1 unowned `hr_questions` |

### Contract verification outcome

From the endpoint matrices in `API_CONTRACT_AUDIT.md` — **41 documented endpoint rows** (some rows group near-identical operations; the 11 alias rows are assessed as a set in §1 of that document):

| Status | Count | Share |
|---|---|---|
| **Working** (contract holds end-to-end) | **23** | 56 % |
| **Inconsistent** (responds, but contract diverges between provider and consumer, or between siblings) | **14** | 34 % |
| **Unused** (implemented, zero callers in the repo) | **3** | 7 % |
| **Incomplete** (partially implemented) | **1** | 2 % |

Plus the WebSocket: **1 socket, and its JSON control contract is broken in one field** (C-06) and untyped/informal in the other direction (M-01).

**So: 23 of 41 REST contracts are verified-intact; 18 are not.** Every one of the four interview modules has at least one broken or unrepresented contract.

---

## 3. Findings

**63 findings** are recorded in `ARCHITECTURE_RISKS.md`, each with the seven mandated fields (file path · function/endpoint · actual implementation · expected behaviour · discrepancy · impact · recommended correction).

| Severity | Count | IDs |
|---|---|---|
| **CRITICAL** | **11** | C-01 … C-11 |
| **HIGH** | **15** | H-01 … H-15 |
| **MEDIUM** | **25** | M-01 … M-25 |
| **LOW** | **12** | L-01 … L-12 |

Sub-registers kept in the per-domain documents (all folded into the 63, not additional): `WS R-01…R-15` (WebSocket races/inconsistencies), `DB-01…DB-18` (database), `4.1–4.8` (REST mismatch register), and the module registers `J-1…J-9`, `H-1…H-12`, `G-1…G-11`, `T-1…T-14`, `P-1…P-11`.

### Evidence discipline notes

- **Two findings are explicitly latent, not active.** C-09 (fabricated nonverbal metrics) and C-10 (fabricated transcripts) are proven by reading the emitter code, and then `[V-live]` confirmed **dormant** because `mediapipe 0.10.13` and `faster_whisper 1.2.1` are installed in the project venv. They become active the moment a deployment fails to install those wheels or the media file is missing. They are rated CRITICAL on *consequence*, and the report says so rather than claiming a present outage.
- **C-10's hardcoded confidence values are, however, live.** `0.94` (Faster-Whisper) and `0.90` (openai-whisper) are constants, so *every* JAM report currently shows a fabricated transcript-confidence percentage.
- **Three findings were disproved during the audit** and are excluded: the PCM frame size genuinely matches at both ends (3200 bytes = 1600 samples = 0.1 s); the WebM socket branch is fully implemented and correctly advances `elapsed` (it is merely unreachable from any client); and `_load_guesstimate_context` *does* read the database — just for round-type gating, not ownership. `[V-live]` `[V]`
- Every count in §2 and the `23/41` split in §2 above are reproducible from the documents themselves.

---

## 4. Per-module integration health

Full flows, field-by-field payload traces and the per-module defect registers are in `MODULE_INTEGRATION_AUDIT.md`.

| Module | Live WS | Live context | Telemetry consumed | Audio actually uploaded | Report shape stable | Ownership enforced | Terminal state handled | **Verdict** |
|---|---|---|---|---|---|---|---|---|
| **JAM** | ✓ connected | ✗ (id **`0`**) | ✗ **written, never read** | ✓ (`.webm` container) | ✗ 3 live shapes | ✗ `/analyze` has no auth dep | ~ | **UNHEALTHY** |
| **HR Behavioral** | ✓ connected | ✗ (arg omitted) | ✓ `/answer` drains Redis | ✗ race (H-07) | ✓ 1 shape | ✗ user resolved, unused (C-03) | ✗ no `else` (H-04) | **AT RISK** |
| **Guesstimate** | ✓ connected | ✓ **only module** | ✓ `/submit` drains Redis + `_LAYAS` | ✗ race (H-07) | ✓ 1 shape, stored twice | ✗ user resolved, unused | ~ | **PARTIALLY HEALTHY** — and its remaining defect is one key name |
| **Technical** | ✓ connected | ✗ (arg omitted) | ✓ `/answer` drains | ✗ **never** (H-08) | ✗ 2 live shapes | ✗ `/audio` fully open (C-04) | ✗ no `else` | **UNHEALTHY** |
| **Coach / Dashboard** | n/a | n/a | n/a | n/a | LLM-authored JSON, unvalidated | ✗ `user_id != 1` bypass (C-05) | ✗ `console.error` only | **AT RISK** |

**No module is fully healthy.** Guesstimate is the closest, and the fact that its headline feature (Socratic live coaching) fails on a `partialTranscript` / `partial_transcript` key mismatch is the clearest single piece of evidence that **the WebSocket contract was never written down anywhere.**

---

## 5. The most dangerous integration risks, ranked

1. **C-01 + C-02 + C-03 + C-04 + C-05 — the auth layer is nominal, and four endpoints skip it entirely.**
   `get_current_user` never rejects: a missing or invalid token silently yields the lowest-id user in the table, or auto-creates `developer@verbaliq.local` / `verbaliq123`. On top of that, `/analyze` has no identity dependency at all, `/api/technical/audio/{filename}` has none, the HR/Technical answer endpoints resolve a user and discard it, and `coach.py:192` contains a literal `and user_id != 1` bypass that anonymous callers inherit. **One class of root cause turns six separate "privilege escalation" findings into "unauthenticated remote access".** The frontend gates every route behind `ProtectedRoute`, so nothing in the UI hints at this.

2. **C-07 + H-04 — HR/Technical round state is a JSON array mutated with no lock, and the client cannot represent the reply.**
   Concurrent `/answer` POSTs silently lose an answer, its evaluation and its audio; `question_count` is *derived from the overwritten array*, so the counter hides the loss. Meanwhile `if (complete) … else if (next_question) …` has **no `else`**, so a reply that is neither leaves the UI on the same question that the server has already consumed and advanced past — inviting a duplicate submit that then over-counts.

3. **C-11 + P-1 — a four-value backend enum against a three-value frontend union, with the `default:` arm mapping the unknown value to its semantic opposite.**
   `progress.py:631` can emit `status: "developing"` for the guesstimate card; `PlacementReadinessMatrix.tsx:30-52` renders it as **"Unattempted"** with an empty-circle icon and a dimmed card. `[V-live]` the audited DB holds two completed guesstimate sessions, so this is reachable with today's data. It sits on the product's headline deliverable, and TypeScript cannot catch it because the value arrives as runtime JSON.

4. **C-06 — the Socratic coaching agent is fed an empty transcript, always, by every client.**
   The client sends `partialTranscript`; the server reads `context["partial_transcript"]`. `question` and `category` arrive fine (and are additionally seeded from `guesstimate_cases` server-side), so tier-2 hints **do appear** — they are simply never about what the candidate said. No error, no log, no failing test. This is the product's differentiator, silently degraded to a rephrasing of the tier-1 scaffold.

5. **C-08 + M-07 — JAM's live telemetry is written to a session id that does not exist, read by nobody, and the whole store is per-process.**
   `RecordingSession.tsx:22` opens `/ws/session/0/emotion` because the row is created only after upload; `analysis.py` never calls `get_session_emotion_summary`; Redis `EXPIRE 3600` deletes the rest. Separately `_LAYAS` and `_LOCAL_BUFFERS` are process-local dicts, so under `--workers > 1` every round's `vocal_delivery` and `laya_metrics` become **all-zeros objects that the UI renders as measurements** (GuesstimateReport's `?? 75`/`?? 70` sub-score fabrications are the same failure class).

6. **C-09 + C-10 — two code paths manufacture evaluation data and persist it indistinguishably from measurement.**
   `_deterministic_fallback` returns `rng.uniform(76,92)` eye contact and `rng.uniform(80,94)` posture keyed off `hash(video_path)`; the analysis exception path hardcodes 82 % / 85 % / −22 dB / "Measured & Structured" plus an entire `avatar_reaction` and `congruence = "High Alignment"`; `MOCK_TRANSCRIPTS` returns a canned paragraph with `confidence: 0.88` — and **the two real Whisper paths also return hardcoded confidences (0.94 / 0.90) that are live today.** A hiring-readiness product asserting measured behaviours that were never measured, feeding `progress.py`'s averages.

7. **C-02 (again) + H-05 + H-14 — a single synchronous process runs the entire ML pipeline on the request path while holding a DB connection.**
   `/analyze` executes Whisper → MediaPipe → Parselmouth → wav2vec2 → an LLM call in one request; `create_session` does blocking 256 KB read loops inside `async def`; there is no job queue, no timeout hierarchy, and the only client signal is a 120-second axios timeout. Two concurrent analyses can stall every live WebSocket.

8. **H-15 + DB-04 — `sessions.report` / `round_metadata` are unversioned, five-writer JSON with four live shapes.**
   Verified in the data: three JAM shapes, two Technical shapes (with `summary` renamed to `executive_summary` and never migrated, so `TechnicalReport.tsx:111` reads a key the current writer no longer emits), and `round_metadata` that is `{}` for HR/Guesstimate/Technical while `progress.py` reads JAM-specific keys out of it. There is no `schema_version` and no migration path — `check_and_apply_migrations()` is five raw `ALTER TABLE`s inside `except Exception: pass`.

---

## 6. Prioritised remediation roadmap

Ordered by (blast radius × user-visible wrongness) ÷ effort. **Nothing here has been started** — per instruction, implementation awaits approval.

### P0 — stop the wrong answers reaching users (est. 1–2 days)
1. **C-06** one-line key alignment (`partialTranscript` → `partial_transcript`), plus a test asserting the server variable is non-empty after a context frame. Cheapest fix in the audit, restores the headline feature.
2. **C-11** add `"developing"` to the union and to a `case`; change the `default:` arm to render the raw value with a neutral style + `console.warn`, so an unmapped enum is *visible* rather than *wrong*.
3. **H-04 / T-04 / T-03** add the terminal `else` in HR and Technical (surface an error and re-fetch `/session/{id}`); sync `max_questions` from the server on restore.
4. **C-09 / C-10 / G-05 / T-05 / H-13** — replace every fabricated-value default (`?? 75`, `?? 8`, `?? 82`, `82.0`, `{"score": 7}`, the mock transcript branch) with an explicit `null` + "not measured" render. Do not let absence look like data.

### P1 — make the boundaries real (est. 3–5 days)
5. **C-01** split `get_current_user` (raises 401) from `get_optional_current_user`; delete the auto-create branch; gate any guest fallback behind a `settings.allow_anonymous_local_drills` flag defaulting `False`; converge the four resolvers; add a route-walk test asserting every non-public route 401s without a header.
6. **C-02, C-03, C-04, C-05** add the missing dependencies and one shared `load_owned_session()` helper across all four round routers; delete the `user_id != 1` clause; remove or auth the open Technical audio route.
7. **C-08** create the session row *before* recording (`POST /api/sessions/intent` → id), pass it to the hook, and have `/analyze` drain that key.
8. **H-02 / M-16** authenticate at the WS handshake (query param or `Sec-WebSocket-Protocol`) before `accept()`; add an `Origin` allow-list.

### P2 — make state writes safe (est. 1 week)
9. **C-07** `with_for_update()` on the round row, or move `questions` into a child table so appends are INSERTs; add a `revision` column with compare-and-set and 409 on mismatch.
10. **H-07 / H-08** make `MediaRecorder.stop()` return `Promise<Blob>` and `await` it before submit (HR, Guesstimate, Technical).
11. **M-07** move `_LAYAS` and `_LOCAL_BUFFERS` into Redis; until then, refuse `--workers > 1` at startup.
12. **H-09 / H-10** reuse the validated `_save_upload` on all three round upload paths (they currently ignore `max_upload_size_mb` and `await audio_file.read()` the whole body); drop client-supplied `overall_score`/`report` from `/api/sessions/json`.

### P3 — contracts as artefacts, not conventions (est. 1–2 weeks)
13. **H-15 / DB-04** per-round Pydantic report models + `report_schema_version` + one backfill migration for `summary` → `executive_summary`; publish OpenAPI and generate the TS types from it (this single change also structurally prevents C-11 and M-21).
14. **M-17** delete the `/api/jam` double-mount (11 aliases, 60 operations for 49 handlers, and an alias set that is *incomplete* — `/api/jam/.../feedback` 404s).
15. **M-13 / M-14** adopt Alembic with real upgrades/downgrades and index creation; add `ondelete="CASCADE"` to every child FK; enable `PRAGMA foreign_keys` via a connect listener. *(Note: on this SQLite host `DELETE /api/sessions/{id}` succeeds via ORM cascade `[V-live]`. Whether it fails once a child row exists under PostgreSQL is **inferred from the DDL and unverified — `[I]` `[U]`, no PostgreSQL instance was reachable during this audit.**)*
16. **H-01** replace the `% 3200` heuristic with an explicit `{type:"init", format:"pcm_s16le", sample_rate:16000, channels:1}` handshake; reject binary before init.
17. **M-11 / M-20** one scoring authority (bands, scales, 1-10 vs 0-100 reconciliation); wire or delete `settings.whisper_model_name`; centralise LLM access (currently triplicated across `requests`, `langchain_openai`, `httpx`).
18. **H-05** move analysis to a background job with a status endpoint; await the emotion warm-up in the lifespan handler.

### P4 — hygiene and operability (est. 2–3 days)
19. **M-08 / L-08** pin `httpx`; declare or drop `ollama`; reconcile `requirements.txt` against the venv (FastAPI 0.147.0 installed vs `==0.104.1` pinned — the drift already changed observable routing behaviour during this audit); delete the unused `asyncpg`.
20. **M-15, M-18, L-04, L-05** fail fast on the default `secret_key`; stop serialising absolute `video_path`/`audio_path`; `datetime.now(timezone.utc)`; annotate `email: EmailStr`.
21. **L-06, L-07, M-19** delete `getFeedback` (zero importers), type `getTechnicalSession`, consume or remove `extended_metrics.mental_math`.
22. **DB-07** add `ix_sessions_round_type`; **M-01** tag every outbound WS frame with a `type`.
23. **L-02, L-03, L-10, L-12** proper resampler, stop routing the mic worklet to `audioCtx.destination`, replace the `setTimeout(…, 150)` PDF print, promote the `_jam` pseudo-key out of `filler_words_list`.

---

## 7. Documents in this audit

| File | Contents |
|---|---|
| `API_CONTRACT_AUDIT.md` | Premise corrections; route-registration architecture and the `/api/jam` alias table; the four identity resolvers; full per-router contract matrices with the mandated Status column; REST mismatch register 4.1–4.8; cross-cutting observations. |
| `WEBSOCKET_CONTRACT_AUDIT.md` | The single socket's lifecycle, binary format both ends, JSON control contract, init/termination, the per-frame processing pipeline, live-vs-post-hoc delivery paths, race/inconsistency register R-01…R-15. |
| `MODULE_INTEGRATION_AUDIT.md` | End-to-end traced flows for JAM, HR, Guesstimate (incl. the Laya loop) and Technical, plus coach/dashboard; per-module defect registers; module health table. |
| `DATABASE_SESSION_AUDIT.md` | Entity inventory from both ORM and **live DDL**; relationship graph and enforced 1:1 invariants; FK non-enforcement; model↔DDL drift; session lifecycle and the three transition defects; transaction boundaries; where every artefact persists; observed duplicate/inconsistent states; migration posture; DB-01…DB-18. |
| `ARCHITECTURE_RISKS.md` | 63 findings, each with the seven mandated fields, severity-classified; plus the architecture-level observations A-1…A-12 for scope G. |
| `AUDIT_SUMMARY.md` | This document. |

### Standing caveats

1. **Everything labelled `[V-live]` reflects the local SQLite *fallback* file** (`backend/speakflow.db`, 19 sessions) — **not the configured datastore.** *Corrected 2026-10-31:* the earlier claim that `.env` defines no `DATABASE_URL` was **wrong**. `backend/.env` **does** define `DATABASE_URL=postgresql://…` (value withheld here), plus `SECRET_KEY`, `REDIS_URL` and `CHROMA_*`. `config.py:25` only supplies the SQLite *default*, which the `.env` value overrides. *Corrected 2026-11-02:* the sentence that followed — "engine.py attempts the PostgreSQL connection at import and, when it fails, logs a single warning and silently rewrites the URL to SQLite" — was true only of the **committed** engine at HEAD `326d75e` (`database/engine.py:25-40`, whose fallback path is built at `:35-36` from `settings.upload_dir.parent / "speakflow.db"`, **not** from `config.py:25`), and it **no longer describes this working tree**. The uncommitted `backend/app/database/engine.py:88-114` validates the configured URL, verifies connectivity once and then **fails closed** with `DatabaseConnectionError` (`:41-47`, `:103-107`); no SQLite fallback branch remains in that file, and `backend/.env` does set `DATABASE_URL=postgresql://…` (verified from the key's value prefix only; the credential is not reproduced here). So the SQLite data is **local-machine evidence captured while that now-superseded fallback was in force on this host** — `backend/speakflow.db` exists (311,296 bytes, mtime 2026-10-31) — not evidence about production, and no longer evidence that the current code can reach SQLite at all. `[V-live]` The PostgreSQL deployment was **never inspected: `[U]`** — no schema, no row counts, no constraint or PRAGMA state. Conclusions that depend on engine behaviour (FK enforcement, delete cascade, nullability drift, index presence) hold **for SQLite as observed only**; whether they also hold, differ, or reverse under PostgreSQL is **unverified**, including M-13 and the `DELETE /api/sessions/{id}` cascade expectation. No PostgreSQL instance was reachable during this audit, so **no PostgreSQL-specific claim in these six documents has been tested.**
2. The audited tree contains **pre-existing uncommitted work** — the entire emotion/Laya/WebSocket feature set among them. Several findings therefore describe code that has not yet been through review. `[V]`
3. Browser-timing-dependent claims (the MediaRecorder `onstop` races, H-07/H-08) are verified **in code ordering**; the observed frequency is `[I]` — not established by running a browser. `[U]`: whether any given browser tolerates the ordering.
4. Frontend TypeScript interfaces were treated as **consumer claims, never as the contract**. Every contract statement is traced to a provider (handler source) and, where the shape is data-dependent, to the live database. `[V]`
5. Speculative items were excluded rather than downgraded. Three candidate findings were actively disproved and are recorded as such (§3, Evidence discipline notes).
