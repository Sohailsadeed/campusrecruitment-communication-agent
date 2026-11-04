# SpeakFlow — Database Schema & Session Lifecycle Audit

**Audit date:** 2026-10-31 · **Branch:** `feature/hr-round` @ `326d75e` (+14 modified / 2 untracked pre-existing files)
**Mode:** strictly READ-ONLY. No source file, row, or schema object was created, altered, or deleted by this audit.
**Evidence tags:** `[V]` verified by reading source · `[V-live]` verified by executing code or querying the live DB read-only · `[I]` inferred · `[U]` unknown / unverifiable

> The schema evidence below comes from two independent sources: the ORM declarations in
> `backend/app/models/*.py`, and the **actual DDL** of `backend/speakflow.db`, dumped with
> `sqlite3.connect('file:speakflow.db?mode=ro', uri=True)` + `PRAGMA table_info/index_list/foreign_key_list`
> and `sqlite_master.sql`. Wherever they disagree, the disagreement *is* the finding.

---

## 1. Entity inventory

10 tables, 345 lines of ORM total. `[V-live]` the live DB has exactly these 10 tables and no others — there is **no** `alembic_version`, no `*_revision`, no legacy table.

| Table | ORM file | Rows `[V-live]` | Role | Owner |
|---|---|---|---|---|
| `users` | `models/user.py:11` | 2 | identity + resume pointer | auth |
| `sessions` | `models/session.py:11` | 19 | **universal round header** | `routes/sessions.py` + each round router |
| `transcriptions` | `models/session.py:70` | 7 | Whisper text (1:1) | `routes/analysis.py` |
| `session_analyses` | `models/session.py:89` | 10 | numeric metrics (1:1) | `routes/analysis.py`, `routes/sessions.py` |
| `ai_feedback` | `models/feedback.py:11` | 7 | LLM feedback (1:N) | `routes/analysis.py` |
| `technical_interviews` | `models/technical.py:11` | 5 | Technical round state (1:1) | `routes/technical.py` |
| `guesstimate_cases` | `models/guesstimate.py:11` | 2 | Guesstimate round state (1:1) | `routes/guesstimate.py` |
| `hr_interviews` | `models/hr.py:11` | 2 | HR round state (1:1) | `routes/hr.py` |
| `hr_questions` | `models/hr.py:34` | 40 | canonical question bank | seeded at startup |
| `curriculum_plans` | `models/coach.py:11` | 3 | coach roadmap (1:N per user) | `routes/coach.py` |

There is **no** table for: emotion telemetry (Redis-only), Laya nudge events (Redis-only), per-question HR/Technical audio (filesystem + a path string inside the JSON `questions` column), filler-word occurrences (JSON inside `session_analyses.filler_words_list`), or RAG chunks (Chroma). `[V]`

### 1.1 Full column map (as actually declared)

**`users`** — `id` PK · `email` VARCHAR(255) UNIQUE NOT NULL · `username` VARCHAR(100) UNIQUE NOT NULL · `hashed_password` VARCHAR(255) NOT NULL · `full_name` VARCHAR(150) NULL · `created_at` · `resume_path` VARCHAR(500) NULL · `resume_name` VARCHAR(255) NULL
The last two were **not** in the original table — `[V-live]` the DDL shows them appended after `created_at` on the same physical line as the `ALTER TABLE` migration produced them:
```sql
CREATE TABLE users (
  id INTEGER NOT NULL, email VARCHAR(255) NOT NULL, username VARCHAR(100) NOT NULL,
  hashed_password VARCHAR(255) NOT NULL, full_name VARCHAR(150),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  resume_path VARCHAR(500), resume_name VARCHAR(255),   -- ← appended by check_and_apply_migrations()
  PRIMARY KEY (id))
```

**`sessions`** — `id` PK · `user_id` FK→`users.id` **NULLable**, indexed · `title` VARCHAR(255) NOT NULL · `description` TEXT NULL · `duration_seconds` FLOAT NOT NULL · `video_path` VARCHAR(512) NULL · `audio_path` VARCHAR(512) NULL · `status` VARCHAR(32) NOT NULL · `created_at` · **`round_type` VARCHAR(32) DEFAULT 'jam'** · **`overall_score` FLOAT NULL** · **`round_metadata` JSON DEFAULT '{}'** · **`report` JSON NULL**

**`transcriptions`** — `id` · `session_id` FK UNIQUE NOT NULL · `text` TEXT NOT NULL · `language` VARCHAR(16) 'en' · `confidence` FLOAT 0.0 · `created_at`

**`session_analyses`** — `id` · `session_id` FK UNIQUE NOT NULL · `speaking_pace` FLOAT · `filler_words_count` INT · `filler_words_list` JSON · `clarity_score` FLOAT · `eye_contact_percentage` FLOAT · `posture_quality` FLOAT · `created_at`

**`ai_feedback`** — `id` · `session_id` FK NOT NULL (**no unique**) · `feedback_type` VARCHAR(64) 'overall' · `content` TEXT · `score` FLOAT · `suggestions` JSON · `created_at`

**`technical_interviews`** — `id` · `session_id` FK UNIQUE NOT NULL · `role` VARCHAR(150) NOT NULL · `target_company` VARCHAR(150) NULL · `resume_context` TEXT · `max_questions` INT (default 5) · `question_count` INT (default 0) · `questions` JSON (default list) · `current_question` JSON NULL · `created_at`

**`guesstimate_cases`** — `id` · `session_id` FK UNIQUE NOT NULL · `question` TEXT NOT NULL · `category` VARCHAR(100) NOT NULL · `difficulty` VARCHAR(50) NOT NULL · `approach_type` VARCHAR(50) NULL · `candidate_answer` TEXT NULL · `audio_url` VARCHAR(512) NULL · `evaluation` JSON NULL · `created_at`

**`hr_interviews`** — same shape as technical minus `resume_context`, plus `interview_mode` VARCHAR(50) default `'standard_hr'`; `max_questions` default 4

**`hr_questions`** — `id` · `question_key` VARCHAR(50) UNIQUE idx · `question_text` TEXT UNIQUE · `category` VARCHAR(100) idx · `difficulty` VARCHAR(50) 'Medium' · `source_type` VARCHAR(50) 'Behavioral' · `keywords` JSON · `rubric` JSON · `created_at`

**`curriculum_plans`** — `id` · `user_id` FK NULLable idx · `target_role` VARCHAR(100) · `roadmap_title` VARCHAR(255) · `status` VARCHAR(32) 'active' · `target_date` **VARCHAR(50)** (a date stored as a string) · `identified_bottlenecks` JSON · `days` JSON · `meta_summary` JSON · `created_at` · `updated_at` (`onupdate=func.now()`)

---

## 2. Relationship graph

```
users (id)
  │  1:N  cascade="all, delete-orphan" (ORM only — see §2.2)
  ▼
sessions (id, user_id NULLable FK)
  ├─ 1:1 transcriptions      session_id UNIQUE NOT NULL
  ├─ 1:1 session_analyses    session_id UNIQUE NOT NULL
  ├─ 1:N ai_feedback         session_id NOT NULL   (no unique)
  ├─ 1:1 technical_interviews session_id UNIQUE NOT NULL
  ├─ 1:1 guesstimate_cases   session_id UNIQUE NOT NULL
  └─ 1:1 hr_interviews       session_id UNIQUE NOT NULL

users (id) ── 1:N curriculum_plans (user_id NULLable FK)   [no cascade on this side]
hr_questions (id) ── orphan reference table, no FK to anything
```

### 2.1 The 1:1 invariants ARE enforced — verified, not assumed

`[V-live]` Every round-detail table's `session_id` is genuinely unique in the physical schema, so "one detail row per session" is a DB guarantee, not just an ORM convention:

| Table | Mechanism | Evidence |
|---|---|---|
| `transcriptions` | table-level `UNIQUE (session_id)` | `sqlite_autoindex_transcriptions_1` unique=1 origin=u |
| `session_analyses` | table-level `UNIQUE (session_id)` | `sqlite_autoindex_session_analyses_1` unique=1 origin=u |
| `technical_interviews` | unique index | `ix_technical_interviews_session_id` unique=1 origin=c |
| `guesstimate_cases` | unique index | `ix_guesstimate_cases_session_id` unique=1 origin=c |
| `hr_interviews` | unique index | `ix_hr_interviews_session_id` unique=1 origin=c |
| `ai_feedback` | **deliberately non-unique** | only `ix_ai_feedback_id` |

> Note the split mechanism: `unique=True` alone (transcriptions, session_analyses) yields a
> table constraint; `unique=True, index=True` (the three round tables) yields a unique index.
> Functionally equivalent in SQLite; **not** identical in how a future migration tool would see them. `[V-live]`

Duplicate check `[V-live]`: `GROUP BY session_id HAVING COUNT(*)>1` → 0 for every table. No orphan detail rows either (§4.2).

### 2.2 Foreign keys are declared but NOT enforced

`[V-live]` A fresh connection to the audited DB reports:
```
PRAGMA foreign_keys → (0,)
```
`backend/app/database/engine.py:20-22` sets only `check_same_thread` for SQLite:
```python
if database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
```
There is no `event.listens_for(engine, "connect")` hook issuing `PRAGMA foreign_keys=ON`, and none exists anywhere in the codebase. `[V]`

**Consequence.** In the *default/local* configuration every FK in §1 is advisory: raw SQL, a future migration script, or any non-ORM writer can insert a detail row pointing at a non-existent session, or delete a user and leave sessions behind. In the *production* configuration (PostgreSQL) FKs **are** enforced by the server. Referential integrity is therefore **environment-dependent**, which is the classic setup for "works locally, fails on deploy" or the reverse. This is a confirmed divergence between the two supported databases, not a speculation. `[V-live]`

**Secondary consequence — the ORM cascade is doing all the work.** `Session` declares `cascade="all, delete-orphan"` on all six relationships (`models/session.py:39,45,48,54,60,66`) and `User` declares it on `sessions` (`models/user.py:28`). Those are *Python-side* semantics: they fire only when the parent is loaded and deleted through a SQLAlchemy `Session`. `[V]` The absence of `ondelete=` on every `ForeignKey(...)` means the DDL reads `ON DELETE NO ACTION`, so a PostgreSQL deployment would not cascade at the database layer `[V]` for the DDL text. Whether that makes **`DELETE /api/sessions/{id}` fail** on a Postgres deployment once any child row exists is **an inference, not a demonstrated result: `[I]` `[U]`** — no PostgreSQL instance was reachable during this audit and the delete was never exercised against one. What *was* observed is that on this SQLite host the delete succeeds, because the ORM cascade is doing all the work `[V-live]`. Treat the PostgreSQL consequence as unverified rather than as a confirmed bug.

**Third:** `CurriculumPlan.user` (`models/coach.py:49`) has **no** `back_populates` and no cascade — deleting a user leaves orphaned plans in the only direction the ORM will not clean up. `[V]`

### 2.3 Nullable contract drift: model vs physical DDL

| Column | ORM declares | Live DDL | Verdict |
|---|---|---|---|
| `sessions.round_type` | `nullable=False` (`session.py:26`) | `round_type VARCHAR(32) DEFAULT 'jam'` → **NULLable** | **DRIFT** `[V-live]` |
| `sessions.round_metadata` | `nullable=False` (`session.py:28`) | `round_metadata JSON DEFAULT '{}'` → **NULLable** | **DRIFT** `[V-live]` |
| `sessions.overall_score` | `Optional` | NULLable | match |
| `sessions.report` | `Optional` | NULLable | match |
| `users.resume_path` / `resume_name` | `Optional` | NULLable | match |
| `technical_interviews.questions` | `Mapped[dict]` + `default=list` (`technical.py:25`) | `questions JSON NOT NULL` | **TYPE ANNOTATION CONTRADICTS DEFAULT** `[V]` |

`check_and_apply_migrations()` (`database/engine.py:64-82`) emits bare `ALTER TABLE … ADD COLUMN` without `NOT NULL`, so columns added by the migration path can never carry the model's `nullable=False`. `[V]` Meanwhile **no constraint is enforced on Postgres either**, because on Postgres the same ALTER text is used (`engine.py:66-79` is dialect-agnostic). `[V]`

**`technical_interviews.questions`** is annotated `Mapped[dict]` (a mapping) but defaulted to `list` and used as a list everywhere (`routes/technical.py`, `agents/interview_graph.py`). The sibling `hr_interviews.questions` is correctly `Mapped[list]` (`models/hr.py:25`). This is a genuine declaration bug in the model, not just a cosmetic one — `flag_modified`-style list mutation on a value the type system believes is a dict. `[V]`

### 2.4 Missing index

`models/session.py:26` declares `round_type … index=True`. `[V-live]` The `sessions` table has only `ix_sessions_id` and `ix_sessions_user_id` — **there is no `ix_sessions_round_type`**. `Base.metadata.create_all` skipped it because the column was added later by `ALTER TABLE`, and `check_and_apply_migrations()` never creates the accompanying index. `[V]`

Impact: every one of `routes/progress.py`'s aggregations filters `Session.round_type == "…"`, and `_user_session_filter` (`progress.py`) is applied on each of the ~10 dashboard endpoints. On the audited 19-row table this is invisible; it is a scan-by-construction on any real dataset. `[V]`

Also missing: no index on `sessions.status`, on `sessions.created_at` (every report page sorts/filters by it), or on `ai_feedback.session_id` (the only child table whose FK column is unindexed — `[V-live]` `ix_ai_feedback_id` is on the PK, nothing on `session_id`). `[V]`

---

## 3. `sessions` is the shared spine — and its two payload columns are unversioned schema soup

`round_metadata: JSON` and `report: JSON` hold **the entire result payload** for all four rounds. Nothing in the codebase declares, validates, or versions their shape. `[V]` The consequence is measurable in the data itself.

### 3.1 `sessions.report` — four distinct shapes observed live

`[V-live]` Distinct key sets across 19 rows:

**JAM** (`routes/analysis.py` → `generate_feedback`), evolving by commit:
```
session  6: cadence_sparkline, competencies, curated_drills, feedback_content, filler_timeline,
         mastery_points, metrics, rewrites, suggestions, total_score, verdict
session  7: + avatar_reaction, congruence, multimodal_timeline, nonverbal_summary
session  9: + prosody
```
→ sessions 6, 7, 9/10 are three different report schemas under the same `round_type='jam'`.

**Technical** — two mutually exclusive shapes under the same `round_type='technical'`:
```
sessions 11, 13: strengths, summary, total_score, weaknesses
sessions 16, 20: avg_conciseness_score, avg_understanding_score, executive_summary,
                 rambling_rate_percent, total_score
```
The summary key **renamed** from `summary` → `executive_summary`. `[V-live]`

`frontend/src/pages/technical/TechnicalReport.tsx:111` reads `reportData.report?.summary` only. Therefore on sessions **16 and 20** (the *current* shape) the executive summary is never displayed — the user sees the client-side default string `"Technical session completed."` — while on 11/13 (the *legacy* shape) `avg_conciseness_score`/`avg_understanding_score`/`rambling_rate_percent` are absent and the `?? 80` / `?? 82` fallbacks at `:260` / `:287` fabricate telemetry. **One report page, two shapes, each half-broken.** `[V-live]` `[V]`

**HR** — one shape, 7 keys: `avg_ownership_score, avg_specificity_score, avg_star_completeness, executive_summary, strengths, total_score, weaknesses` (`routes/hr.py` → `generate_hr_report`). `[V-live]`

**Guesstimate** — `session.report` is written directly from `eval_result` (`routes/guesstimate.py`), so the report column and `guesstimate_cases.evaluation` hold **the same payload twice**. `[V]`

> Cross-module naming inconsistency, confirmed: HR and Guesstimate use `executive_summary`, JAM uses `feedback_content`, Technical used `summary` and now uses `executive_summary`. There is no shared schema; each round's report page hardcodes its own key. `[V]`

### 3.2 `sessions.round_metadata` — same drift

`[V-live]`
```
jam  4, 5: {}                                              ← earliest
jam  6: cardinal_infractions, category, hesitation_count, pause_count, pause_time,
        repetition_count, speaking_pace, topic
jam  7, 8: + eye_contact_percentage, fidget_count, hand_gestures_count, persona,
           posture_quality, target_wpm
jam  9,10: + prosody_confidence, tone_verdict, vocal_energy_db
jam 14,15,19: {mode}                                       ← written by a *different* code path
technical 11,12,13: {role, target_company}
technical 16,20: {}      guesstimate 17,21: {}      hr 18,22: {}
```
Two conclusions:
1. The JAM `round_metadata` schema is append-only-by-commit with no version marker — there is no `schema_version` key anywhere. `[V-live]`
2. **HR, Guesstimate and the current Technical path write `{}`**, because they persist their state in their own detail tables. So any consumer that reads `round_metadata` generically (e.g. `routes/progress.py` reading `persona`/`target_wpm`, or `RecordingSession.tsx` sending them) only ever works for JAM. `[V-live]` `[V]`

`round_metadata` for jam 14/15/19 = `{"mode": …}` is written by `POST /api/sessions/json` (`routes/sessions.py`), i.e. a **second, independent writer** of the same column with a **third** schema. `[V]`

---

## 4. Session lifecycle & status transitions

### 4.1 Status is an unbounded free string

`models/session.py:25` → `status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)`. `[V]`
- **No DB CHECK constraint** — `[V-live]` confirmed in the DDL.
- **No Python enum** — there is no `class SessionStatus` in the backend at all.
- `schemas/session.py` `SessionUpdate.status: Optional[str]` — a client may `PATCH` any string. `[V]`
- The *frontend* is the only place the vocabulary is enumerated: `types/index.ts` `SessionStatus = "pending" | "processing" | "in_progress" | "completed" | "failed"`. `[V]` This is a contract enforced **only** by TypeScript, on the wrong side of the wire — exactly the "do not assume frontend interfaces represent the backend contract" case.

### 4.2 Observed transitions `[V-live]`

Live distinct values: **`completed` (17 rows), `in_progress` (1 row: session 12)**. No row in `pending`, `processing`, or `failed` exists in the audited DB.

The two status-writing state machines:

**A. JAM / legacy analysis pipeline** — `routes/analysis.py:post /{session_id}/analyze`
```
pending ──(set status="processing"; commit)──▶ processing
   processing ──(Whisper → analyze_transcription → analyze_video →
                 analyze_audio_prosody → analyze_speech_emotion → generate_feedback;
                 write transcriptions + session_analyses + ai_feedback
                 + sessions.overall_score/round_metadata/report; commit)──▶ completed
   any exception ──(logger + status="failed"; commit)──▶ failed
```
The `status="processing"` write is committed *before* the CPU-heavy work, which is what makes `AnalysisPage.tsx:39-41`'s `Loading` branch correct — `[V]` but see §4.4 for the crash hole.

**B. Round state machines** — each round router writes status itself:
```
HR:        /start → "in_progress" → /answer (per question) → last answer → "completed"
Technical: /start → "in_progress" → /answer → last answer → "completed"
Guesstimate: /start → "in_progress" → /submit → "completed"
JAM:       POST /api/sessions → "pending" → /analyze → … → "completed"
JAM(json): POST /api/sessions/json → "completed"  ← written directly, skips the whole machine
```
`[V]` for each assignment site (`routes/hr.py`, `routes/technical.py`, `routes/guesstimate.py:188`, `routes/sessions.py` `/json`).

### 4.3 The three confirmed lifecycle defects

**(1) `pending → completed` teleport.** `POST /api/sessions/json` accepts a client-built session and stamps `status="completed"` with no analysis ever running. `[V]` Live proof: sessions **14, 15, 19** are `round_type='jam', status='completed'` with `overall_score IS NULL`, `report IS NULL`, **0 transcriptions, 0 ai_feedback, 0 video, 0 audio** — only a `session_analyses` row. `[V-live]` `AnalysisPage.tsx:15-21` will *not* re-analyse them (its guard requires `status === "pending"`), and `AnalysisResults.tsx` renders them entirely from hardcoded fallbacks (`:120` default score 84, `:132-139` derived competencies, `:164-173` sample rewrites, `:212-221` invented mastery points and drills). **A "completed" session that was never analysed, and a report page that cannot tell the difference.** `[V-live]` `[V]`

**(2) `processing` is terminal on hard crash.** The write is committed before the work (`analysis.py`), and the `except` that sets `failed` only covers exceptions that reach the handler. A process kill, OOM, or the blocking-upload stall noted below leaves the row pinned at `processing` forever. There is **no startup sweep** — `main.py` startup only does `create_all`, `check_and_apply_migrations`, `seed_hr_questions`, and the emotion warm-up task. `[V]` `AnalysisPage.tsx:39` maps `processing` to an indefinite `Loading` spinner with no timeout and no escape hatch. **A stuck session is unviewable and unrecoverable from the UI.** `[V]` `[I]` for the spinner-forever UX outcome given that code.

**(3) No transition validation anywhere.** Nothing checks the current status before writing a new one. `POST /{id}/analyze` can be re-invoked on a `completed` session, overwriting `transcriptions`, `session_analyses`, `ai_feedback`, `overall_score`, `round_metadata` and `report` — and, because HR/Guesstimate/Technical never create those children, re-analysing an HR session with the JAM analysis endpoint writes a **JAM-shaped `report` onto an HR session**, mutating `round_metadata` too. The only guard is the `AnalysisPage` client-side `status === "pending"` check. `[V]` No endpoint requires `round_type == "jam"`. `[V]`

### 4.4 Ownership of creation vs. update is split and inconsistent

| Round | Who INSERTs `sessions` | Who UPDATEs status | Who writes `report` |
|---|---|---|---|
| JAM (video) | `POST /api/sessions` (sessions.py) | `POST /api/sessions/{id}/analyze` | analysis.py |
| JAM (json) | `POST /api/sessions/json` | `POST /api/sessions/json` **directly** | — (never) |
| HR | `POST /api/hr/start` (hr.py) | hr.py `/answer` | hr.py |
| Technical | `POST /api/technical/start` | technical.py `/answer` | technical.py |
| Guesstimate | `POST /api/guesstimate/start` | guesstimate.py `/submit:188` | guesstimate.py (`= eval_result`) |
| WebSocket | **nobody** — requires a pre-existing id | never writes status | never |

`[V]` Two implications:
- The emotion WebSocket (`emotion_stream.py`) is **keyed by `session_id` in the URL but never creates, loads, or validates that row**. It writes only to Redis under `emotion:session:{id}`. A client can stream against session id `999999` (non-existent) and receive a valid telemetry stream; conversely `RecordingSession.tsx:22` passes **`0`** as the session id for the entire JAM recording, because the session is only created *after* upload — see §4.5. `[V]`
- `routes/guesstimate.py` writes the **same dict to two places** (`guesstimate_cases.evaluation` and `sessions.report`), so the two can diverge on any later partial update. `[V]`

### 4.5 The JAM telemetry lifecycle is orphaned by construction

`frontend/src/components/Recording/RecordingSession.tsx:22`:
```ts
const { liveEmotion } = useLiveEmotionStream(0, isRecording, undefined, recorder.stream);
```
`[V]` Sequence: record (WS open on `/ws/session/0/emotion`, Redis accumulating under `emotion:session:0`) → stop → `uploadSession()` creates the row and returns a **new** id → `analyze(id)` → navigate. The Redis buffer written during recording lives permanently under key `emotion:session:0`; nothing ever reads it, and nothing ever migrates it to `emotion:{real_id}`. `[V]` Combined with `EXPIRE 3600` (`emotion_stream.py`) it self-deletes an hour later. `[V]`

**This is a lifecycle defect, not just a WS defect**: JAM is the one round whose live emotional telemetry is generated and then discarded. Confirmed independently in §7 of `WEBSOCKET_CONTRACT_AUDIT.md` and by grep: `routes/analysis.py` never calls `get_session_emotion_summary`. `[V]`

### 4.6 Non-atomic, multi-commit transaction boundaries

`get_db()` (`database/engine.py:44-53`) yields one session per request, `rollback()` on exception, `close()` always. `[V]` But the round endpoints issue **many intermediate commits inside one request**, so a failure mid-way leaves a partially-advanced state:

- `routes/hr.py` `/answer`: transcribe → evaluate → append to `hr.questions` (JSON) → `hr.question_count = len(...)` → write `session.report` → `session.status="completed"` → `db.commit()`. `[V]`
  The read-modify-write on the JSON column is:
  ```python
  updated_questions = list(hr.questions or [])
  updated_questions.append(completed_question)
  hr.questions = updated_questions
  ```
  Reassigning the attribute *does* mark it dirty (unlike `.append()` on the loaded list), so the write lands — but there is **no row lock, no `SELECT … FOR UPDATE`, no version column and no `flag_modified`**. Two concurrent `/answer` POSTs for the same HR session both read `questions = [q1]`, both append, and the later commit silently overwrites the earlier: **one answer, its score, and its `question_count` are lost with no error**. `[V]` Same pattern in `routes/technical.py`. `[V]`
- `routes/technical.py` `resume/upload`: `db.commit()` for the user columns happens **before** `store_performance(...)` (Mem0/Chroma). If Mem0 raises, the DB says a resume exists while the vector store does not. `[V]` Conversely `DELETE /resume` nulls the DB columns and commits but **never deletes the Chroma collection** — so re-uploading the same PDF re-adds to a collection that still contains the old chunks. `[V]`
- `routes/analysis.py`: children (`transcriptions`, `session_analyses`, `ai_feedback`) and the parent (`sessions.status="completed"`) are written in one commit at the end, so *that* step is atomic. `[V]` The `processing` commit is separate — that's the split described in §4.3(2).
- `check_and_apply_migrations()` wraps everything in `except Exception: pass` (`database/engine.py:82-84`) and calls `conn.commit()` twice mid-flight. A failure after the first `ALTER` leaves the schema **partially migrated with the error swallowed** — and the app then starts and fails later with an opaque `OperationalError`. `[V]`

### 4.7 Cascade / deletion paths

`DELETE /api/sessions/{id}` (`routes/sessions.py`) → `_get_session_for_user` → `db.delete(session)` → `db.commit()`. `[V]` Because of the six `cascade="all, delete-orphan"`, ORM-loaded children are deleted. **The media file on disk is not deleted** — `video_path`/`audio_path` strings vanish, the `.webm` remains in `upload_dir` forever. `[V]` No endpoint deletes a user, so `User.sessions` cascade is dead code in practice. `[V]` `[I]` "in practice" = no `/auth/delete` route exists.

`hr_questions` (40 rows, seeded) is never deleted and has no owner — a genuine global table. `seed_hr_questions(db)` runs on every startup and is idempotent only because `question_key` is UNIQUE. `[V]` `[V-live]` `count(distinct question_key) == count(*) == 40`. `[I]` for idempotency relying on the unique index — that is what the DDL supports.

---

## 5. Where answers, transcripts, evaluations and feedback actually persist

| Artifact | Canonical storage | Secondary copy | Verified? |
|---|---|---|---|
| JAM audio/video | filesystem `upload_dir`, path string in `sessions.video_path` | **`audio_path` is NULL for every JAM row** `[V-live]` (sessions 4-10 have `video_path`, none have `audio_path`) — `session_media.py` falls back to `video_path` | `[V]` `[V-live]` |
| JAM transcript | `transcriptions.text` (+ `confidence`) | `sessions.report.feedback_content` quotes it; `words`/`segments`/`pauses` from Whisper are **discarded**, never persisted | `[V]` |
| JAM metrics | `session_analyses` (6 numeric cols) | `sessions.round_metadata` (14+ keys) + `sessions.report.metrics/prosody` | `[V]` |
| JAM filler timeline | `sessions.report.filler_timeline` (cap 15) | `session_analyses.filler_words_list` — **which also carries a `_jam` pseudo-key** that `AnalysisResults.tsx:233-243` depends on | `[V]` |
| Per-word timestamps | **not persisted** | — | `[V]` |
| HR answers | `hr_interviews.questions` JSON array, each element `{…, answer, evaluation, audio_url, track?}` | `sessions.report` (aggregate) | `[V]` |
| HR per-question audio | filesystem, path inside the JSON element | not a column | `[V]` |
| Technical answers | `technical_interviews.questions` JSON | `sessions.report` | `[V]` |
| Guesstimate answer | `guesstimate_cases.candidate_answer` (TEXT) | inside `evaluation` **and** `sessions.report` | `[V]` |
| Live emotion | **Redis only** (`emotion:session:{id}`, EXPIRE 3600) or in-process `_LOCAL_BUFFERS` (cap 5000) | `guesstimate_cases.evaluation.vocal_delivery` (drained, i.e. consumed-once) | `[V]` |
| Laya nudge metrics | Redis only | `evaluation.laya_metrics` | `[V]` |
| Curriculum days | `curriculum_plans.days` JSON | — | `[V]` |
| RAG resume chunks | Chroma (`user_{id}`, `mem0_memories`) | `users.resume_path` | `[V]` |

**Nothing in the DB records that a WebSocket session ever existed.** There is no `emotion_sessions`, no `nudge_events`, no `live_telemetry` table. `[V]` Live vocal telemetry is therefore **non-reproducible and non-auditable**: once `/submit` drains Redis, or once the 1-hour TTL expires without a submit, the data is gone and only the derived aggregate survives (for Guesstimate only). `[V]`

---

## 6. Duplicate and inconsistent states observed in the live data

`[V-live]` All of these are present in the audited DB right now, i.e. reachable, not theoretical.

1. **`status='completed'` with `overall_score IS NULL` and `report IS NULL`** — sessions 14, 15, 19 (JAM/json path) and **sessions 4, 5** which have full transcription+analysis+feedback but `report IS NULL` (they predate the `report` column). `[V-live]` → `AnalysisResults.tsx:120` falls back to `score 84`; the whole screen is fabricated. `[V]`
2. **Two report shapes per round_type** — §3.1. `[V-live]`
3. **Three `round_metadata` shapes for JAM** — `{}`, `{8 keys}`, `{14 keys}`, plus `{mode}` from the json path. `[V-live]`
4. **Duplicate re-runs with identical scores** — guesstimate 17 & 21 both `85.0`; HR 18 & 22 both `91.0`; technical 13, 16, 20 all `88.0`. Consistent with either genuine repeat practice or a re-submit that re-evaluated the same payload. `[V-live]` `[U]` which — the schema carries no `attempt_of`/`revision` link, so **the DB cannot distinguish a retry from a re-attempt**. `[V]`
5. **`round_type='jam'` for sessions 14/15/19 that carry `{"mode": …}` and no media** — these are not JAM recordings at all; they default to `'jam'` because the column's `DEFAULT 'jam'` applies. So **`round_type='jam'` now means "unspecified round"** in the aggregate, and `progress.py`'s JAM card counts them. `[V-live]` `[V]`
6. **7 of 19 sessions (37%) have `user_id IS NULL`** (sessions 4-10) → the ownership guard `_get_session_for_user` skips the check entirely for NULL-owner rows, so they are readable by **every** authenticated user, and the guest list filter (`sessions.py`, `user_id == 1`) and `_user_session_filter` in `progress.py` (`user_id == 1 OR IS NULL`) both deliberately include them. `[V]` `[V-live]`
7. **`curriculum_plans`**: user 1 holds 1 `active` + 2 `archived`. Correct — but the "active plan" lookup relies on `status == "active"` with no unique partial index, so two concurrent `/api/coach/generate` calls can create **two active plans for the same user**, after which `/active` returns an arbitrary one (ordering not guaranteed by a partial index). `[V]` `[I]` for the race outcome.
8. **`technical_interviews.resume_context`** duplicates the retrieved RAG text that also lives in Chroma; two sources of truth for the same string. `[V]`

---

## 7. Migration & schema-management posture

There is **no migration tool**. `[V]` `requirements.txt` has no `alembic`. `[V]` Schema creation is:

```
main.py startup → Base.metadata.create_all(bind=engine)      # tables that do not exist
                → check_and_apply_migrations()               # 5 hand-written ALTER TABLE ADD COLUMN
                → seed_hr_questions(db)
```

`[V]` `database/engine.py:56-84`. Properties of this design:

| Property | Status |
|---|---|
| Reversible | ✗ none of the ALTERs have a downgrade |
| Versioned | ✗ no `alembic_version`, no marker row, no schema hash |
| Idempotent | ~ `hasattr(col)` guard exists per column, so re-running is safe |
| Index-maintaining | ✗ added columns' `index=True` is silently dropped → §2.4 |
| Constraint-maintaining | ✗ added columns cannot be `NOT NULL` → §2.3 |
| Atomic | ✗ two mid-flight commits, whole body under `except Exception: pass` |
| Applies to existing columns | ✗ only these 5 column additions exist; **renames/retypes are impossible** |
| Handles the `summary` → `executive_summary` rename | ✗ it is a *data* change; nothing migrated it → §3.1 live split |

**The `CREATE TABLE … DEFAULT '{}'` for a JSON column** — SQLite accepts `JSON` as a type name and stores text; the ORM's `JSON` type serialises in Python. `[V]` Under **PostgreSQL** `mapped_column(JSON)` maps to `JSON` (not `JSONB`), and `DEFAULT '{}'` renders as `DEFAULT '{}'` — valid, but the `ALTER TABLE … ADD COLUMN round_metadata JSON DEFAULT '{}'` text is dialect-shared, so the same hand-written SQL runs against both engines with no abstraction. `[V]` `[I]` for Postgres acceptance of that exact literal.

---

## 8. Findings register (database-specific; cross-referenced into `ARCHITECTURE_RISKS.md`)

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| DB-01 | **CRITICAL** | HR/Technical JSON-array read-modify-write with no lock or version → lost answers under concurrency | `routes/hr.py`, `routes/technical.py` `[V]` |
| DB-02 | **HIGH** | `PRAGMA foreign_keys=0`: FKs unenforced on the default engine; `ondelete=` absent, so cascade behaviour is engine-dependent. Verified on this SQLite host: `DELETE /api/sessions/{id}` succeeds via ORM cascade `[V-live]`. **Failure under PostgreSQL once children exist is inferred from the `ON DELETE NO ACTION` DDL and unverified — `[I]` `[U]`, no live PostgreSQL instance was tested** | `engine.py:20-22`, DDL `[V-live]` `[V]` |
| DB-03 | **HIGH** | `sessions.status` is a free VARCHAR with no enum/CHECK; frontend TS union is the only validator; `/api/sessions/json` writes `completed` directly; no sweep for stuck `processing` | `session.py:25`, DDL, `analysis.py`, `types/index.ts` `[V]` |
| DB-04 | **HIGH** | `report` / `round_metadata` are unversioned, multi-writer JSON with 4 (report) and 4 (metadata) live shapes; `summary`→`executive_summary` rename never migrated | `[V-live]` §3.1, §3.2 |
| DB-05 | **HIGH** | Re-running `/analyze` on an HR/Technical/Guesstimate session overwrites `report` + `round_metadata` with a JAM-shaped payload; no `round_type` guard | `routes/analysis.py` `[V]` |
| DB-06 | **MEDIUM** | Model/live-DDL drift: `round_type` and `round_metadata` declared `nullable=False`, NULLable in DB | `[V-live]` §2.3 |
| DB-07 | **MEDIUM** | `ix_sessions_round_type` missing despite `index=True` — every dashboard query scans | `[V-live]` §2.4 |
| DB-08 | **MEDIUM** | `technical_interviews.questions` annotated `Mapped[dict]` but defaulted/used as `list` | `technical.py:25` `[V]` |
| DB-09 | **MEDIUM** | No DB row records a WebSocket/emotion/Laya session; telemetry is Redis-with-1h-TTL, drained on read → unreproducible | `emotion_stream.py` `[V]` |
| DB-10 | **MEDIUM** | `DELETE /api/sessions/{id}` leaves the media file on disk; `DELETE /api/technical/resume` leaves the Chroma collection | `routes/sessions.py`, `routes/technical.py` `[V]` |
| DB-11 | **MEDIUM** | `resume/upload` commits DB state before the Chroma/Mem0 write; failure desynchronises the two stores | `routes/technical.py` `[V]` |
| DB-12 | **MEDIUM** | `CurriculumPlan`↔`User` has no back_populates/cascade, and no partial unique index on `(user_id) WHERE status='active'` → orphan plans + possible dual-active race | `models/coach.py:49` `[V]` |
| DB-13 | **MEDIUM** | Guesstimate writes the identical evaluation dict into `guesstimate_cases.evaluation` **and** `sessions.report` | `routes/guesstimate.py` `[V]` |
| DB-14 | **MEDIUM** | 37% of JAM rows have `user_id NULL`, making them globally readable; `round_type='jam'` also silently means "unspecified" via the column DEFAULT | `[V-live]` §6.6, §6.5 |
| DB-15 | **LOW** | No index on `sessions.status`, `sessions.created_at`, `ai_feedback.session_id` | `[V-live]` |
| DB-16 | **LOW** | No attempt/revision link → a retry and a re-attempt are indistinguishable in the data | `[V]` |
| DB-17 | **LOW** | `hr_questions` is a global unowned table reseeded on every boot; safe only because of the UNIQUE index | `[V]` `[V-live]` |
| DB-18 | **LOW** | `check_and_apply_migrations()` swallows all exceptions, can leave the schema half-migrated | `engine.py:82-84` `[V]` |

---

## 9. Caveats on this section's evidence

1. All `[V-live]` schema/data claims describe **`backend/speakflow.db` — the local SQLite *fallback* file**, not the configured datastore. *Corrected 2026-10-31:* this caveat previously stated that `.env` defines no `DATABASE_URL` and cited `config.py:14` as the SQLite default — **both were wrong.** `backend/.env` **does** define `DATABASE_URL=postgresql://…` (value withheld); the SQLite default is at **`config.py:25`** and is *overridden* by that `.env` value. *Corrected 2026-11-02:* the next sentence — "`engine.py:27-40` attempts the PostgreSQL connection at import and, on failure, logs one warning and silently rewrites the URL to `sqlite:///<backend>/speakflow.db`" — described only the **committed** engine at HEAD `326d75e`, whose fallback block is `engine.py:25-40` and whose SQLite path is constructed at `engine.py:35-36` from `settings.upload_dir.parent / "speakflow.db"` — **not** from `config.py:25`, which the earlier wording conflated with it. That sentence **no longer describes this working tree**: the uncommitted `backend/app/database/engine.py:88-114` resolves and validates the configured URL, performs one `verify_connectivity()` (`:82-85`) and otherwise raises `DatabaseConnectionError` (`:41-47`, `:103-107`); no SQLite fallback branch survives in the file. `backend/.env` was re-checked read-only and does set `DATABASE_URL=postgresql://…` (value prefix only; the credential is not reproduced). These observations are therefore **local-machine evidence captured while that now-superseded fallback was in force on this host** — `backend/speakflow.db` is present (311,296 bytes, mtime 2026-10-31) — and say nothing about the PostgreSQL schema or rows. `[V-live]` The PostgreSQL deployment was **not** inspected: `[U]`. §2.2, §2.4 and §7 are valid **for SQLite as observed only**. DB-02's PostgreSQL consequence — FKs enforced while `ON DELETE CASCADE` is absent, and whether `DELETE /api/sessions/{id}` therefore fails once child rows exist — is **inferred from the shared DDL and unverified at runtime** `[I]`; no PostgreSQL instance was reachable during this audit, so it must not be treated as established behaviour.
2. The 19 rows are development fixtures. They prove the drift is *reachable*, not that production data looks like this. `[V]`
3. `confidence` values in `transcriptions` are **not** measured (see `API_CONTRACT_AUDIT.md`: 0.94 / 0.90 / 0.88 are hardcoded in `services/transcription.py`). A `transcriptions.confidence = 0.88` row is the fabricated-mock path, not a measurement — `[V]` `faster_whisper 1.2.1` is installed, so no row in this DB currently comes from that path. `[V-live]`
