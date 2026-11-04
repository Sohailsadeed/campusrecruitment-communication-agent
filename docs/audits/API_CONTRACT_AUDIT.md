# SpeakFlow — REST API Contract Audit

**Audit date:** 2026-10-31 · **Mode:** READ-ONLY — no source file modified, created or deleted.
**Tree:** `feature/hr-round` @ `326d75e` + uncommitted working-tree changes (see `WEBSOCKET_CONTRACT_AUDIT.md` §9).
**Tags:** **[V]** read the code · **[V-live]** confirmed by executing the app (FastAPI `TestClient` against the real venv + `speakflow.db`) · **[I]** inferred · **[U]** unknown.

## 0. Premise corrections (the brief's assumptions vs. reality)

| Assumed by the tasking | Actual | Tag |
|---|---|---|
| "Java backend" calling a Python AI service over HTTP | **No Java anywhere.** One single-process **FastAPI** app (`backend/main.py`) that imports and calls every AI service in-process. | [V] |
| Separate Python AI/NLP microservice tier | **Does not exist.** `backend/app/services/*` are ordinary Python modules, not services. External calls go only to Ollama, OpenRouter, ChromaDB, Redis, edge-tts, and HuggingFace model downloads. | [V] |
| "Pydantic-validated service contracts" | Partially. Route *request* bodies use Pydantic; **no route response uses `response_model` except the legacy `/api/sessions*` family.** All four module routes are annotated `-> dict` and return hand-built dicts. LLM output is parsed with `json.loads` + `.get()` and is **not** schema-validated. | [V] |
| Multimodal/CV runs live | Post-hoc only, inside `POST /analyze`. Nothing video-related crosses the WebSocket. | [V] |

---

## 1. Route registration architecture **[V]**

`create_app()` in [main.py:58-123](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/main.py#L58) mounts 10 routers. Two of them are mounted **twice**:

```python
app.include_router(sessions.router)                       # -> /api/sessions…
app.include_router(analysis.router)                       # -> /api/sessions… (same prefix!)
app.include_router(feedback.router)                       # -> /api/sessions… (same prefix!)
app.include_router(progress.router)
app.include_router(sessions.router,  prefix="/api/jam")   # -> /api/jam/api/sessions…
app.include_router(analysis.router,  prefix="/api/jam")   # -> /api/jam/api/sessions…
app.include_router(technical.router); app.include_router(guesstimate.router)
app.include_router(hr.router); app.include_router(coach.router)
app.include_router(emotion_stream.router)                 # -> /ws/… (no prefix)
```

Three routers (`sessions`, `analysis`, `feedback`) share the literal prefix `/api/sessions` and are distinguished only by sub-path. **[V-live]** The generated OpenAPI document resolves **60 REST operations across 54 paths** — 49 genuine operations plus **11 `/api/jam/api/sessions/...` aliases**.

**The `/api/jam` alias set is a documented-in-name-only dead surface.** No file in `frontend/src` contains the string `api/jam` **[V]**, and because `feedback.router` is *not* re-mounted, the alias family is incomplete:

| | Canonical | `/api/jam` alias |
|---|---|---|
| sessions 7 ops | ✅ | ✅ duplicated |
| analysis 4 ops | ✅ | ✅ duplicated |
| feedback 1 op (`/{id}/feedback`) | ✅ | ❌ **404** [V-live] |

**[V] Two identical handler bodies are now reachable under two URLs.** They are the same function object, so they cannot diverge in behaviour today, but any future change to `sessions.py`/`analysis.py` silently applies to both, and the `JAM Round` tag in `/docs` duplicates 11 entries. Comment in `main.py:80` calls this "Blueprint alignment" — it is Flask-blueprint thinking applied to FastAPI, where it is unnecessary.

**[V]** `app/routes/__init__.py` `__all__` omits `coach` and `emotion_stream`, though `main.py:15` imports them explicitly, so the omission is cosmetic only.

---

## 2. Authentication & authorisation contract **[V]**

Three *incompatible* identity resolvers coexist:

| Resolver | Definition | Behaviour when the bearer token is absent **or invalid** | Used by |
|---|---|---|---|
| `me()` | [auth.py:84-95](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/auth.py#L84) | **401** — strict | `GET /api/auth/me` [V-live 401] |
| `get_optional_current_user()` | auth.py:98-108 | returns `None` (true guest) | `GET /api/technical/resume/status` |
| `get_current_user()` | auth.py:111-136 | **falls back to `SELECT … ORDER BY id ASC` → the first user in the DB**, and if that table is empty **auto-creates** `developer@verbaliq.local` / bcrypt password `verbaliq123` | `/api/hr/*`, `/api/technical/*`, `/api/guesstimate/*` start/answer/submit |
| `_get_optional_user()` (duplicate) | [sessions.py:67-83](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L67) | returns `None`; callers then hard-filter `user_id == 1` | `/api/sessions*`, `/api/progress*`, `/api/coach*` |

### 2.1 Confirmed defects in this layer

- **[V] `get_current_user` never rejects a bad token.** An expired/forged JWT falls through to the first-user branch. A request from *anyone* therefore **writes HR / Technical / Guesstimate sessions and Curriculum data under whichever user has `id = 1`**. This is silent cross-account attribution, not a crash — 19 sessions currently exist, 7 with `user_id = NULL`.
- **[V] `_get_optional_user` duplicates `get_optional_current_user`** — same logic, re-implemented with its own inline `jwt.decode` in `sessions.py`, and re-imported by `coach.py:18` and `progress.py:13`. Two functions, one concept, drifting in opposite directions.
- **[V] `list_sessions` leaks:** with no token it returns `user_id == 1 OR user_id IS NULL`; there is no "deny", only "assume sandbox user 1".
- **[V] `_get_session_for_user` (sessions.py:211-218) skips the ownership check whenever `session.user_id is None`** → the 7 NULL-owner sessions are readable/patchable/deletable by *any* caller.
- **[V] `analysis.py` has no user dependency at all.** `POST /api/sessions/{id}/analyze` — the most expensive endpoint in the app (Whisper + audEERING + Praat + MediaPipe + Ollama) — is callable by anyone for any session id, and **overwrites** that session's transcript, analysis, feedback, `overall_score`, `report` and `status`.
- **[V] `hr.py` / `technical.py` / `guesstimate.py` all `Depends(get_current_user)` but then ignore it for authorisation.** They do `db.get(SessionModel, session_id)` and check only `round_type`. Verified in `hr.py:120-126`, `technical.py:241-247`, `guesstimate.py:122-128`. Any authenticated-or-anonymous caller can submit answers into, and read the full report of, another candidate's session by guessing an integer id.
- **[V] Unauthenticated file serving:** `GET /api/technical/audio/{filename}` (technical.py:435-444) has **no auth dependency whatsoever**, unlike its `/api/hr/audio/` and `/api/guesstimate/audio/` siblings which require `get_current_user`. Path traversal is correctly prevented by `Path(filename).name`, but the authorisation model is inconsistent across three structurally identical endpoints.
- **[V] Coach authorisation has a magic-number hole:** `coach.py:192` — `if not plan or (plan.user_id and plan.user_id != user_id and user_id != 1)` — user 1 can mutate *any* plan, and `_resolve_user_id(None) → 1` means an anonymous caller *is* user 1.
- **[V]** `settings.secret_key` defaults to the literal `"CHANGE_ME_SET_SECRET_KEY_ENV_VAR_IN_PRODUCTION"` (config.py:28). A `.env` with a `SECRET_KEY` key exists in `backend/`, so production risk is [U]; but nothing in code refuses to start on the default, despite the comment "no insecure default".
- **[V]** `create_access_token` uses `datetime.utcnow()` (auth.py:30) — deprecated in 3.12 and naive-vs-aware comparisons raise later.
- **[V]** `UserBase.email` is typed `str` with `min_length=3`; `EmailStr` is imported but unused (schemas/user.py:5,9) — any string containing `@`-noise registers.

---

## 3. Contract matrix — 60 operations

Legend — **Auth**: `None` = no dependency, `Opt` = optional/guest-tolerant, `Req` = `get_current_user` (with the silent fallback of §2), `Hdr` = manual bearer parse. **Persistence**: ORM tables touched. **Status**: Working / Inconsistent / Incomplete / Unused.

### 3.1 Auth — `router = APIRouter(prefix="/api/auth")`

| Endpoint | Method | Auth | Request | Response (exact keys) | Persistence | Status |
|---|---|---|---|---|---|---|
| `/api/auth/register` | POST | None | `UserCreate` JSON: `email:str(3-255)`, `username:str(3-100)`, `full_name:str?`, `password:str(6-128)` | `Token` **201**: `access_token:str`, `token_type:str="bearer"`, `user:{id:int,email,username,full_name?,resume_name?,created_at:datetime}` | `users` INSERT | Working |
| `/api/auth/login` | POST | None | `UserLogin`: `email:str(1-255)` — accepts *email or username*, `password:str` | `Token` 200 / **401** `{detail:"Invalid email or password"}` | read | Working. Note: `email.strip().lower()` then `func.lower(...)` on both columns [V] |
| `/api/auth/me` | GET | Hdr | header `Authorization: Bearer <jwt>` | `UserOut` / **401** / **404** | read | Working [V-live 401] |

### 3.2 Sessions (JAM) — `prefix="/api/sessions"`, also aliased under `/api/jam/api/sessions` **[V-live]**

| Endpoint | Method | Auth | Request | Response | Persistence | Status |
|---|---|---|---|---|---|---|
| `/api/sessions` | GET | Opt | query `limit:int=50`, `offset:int=0`, `round_type:str?` | `List[SessionOut]` | `sessions` read | **Inconsistent** — frontend `listSessions()` passes no params [V] |
| `/api/sessions` | POST | Opt | **multipart**: `title:str(req)`, `description:str?`, `duration_seconds:float=0.0`, `round_type:str="jam"`, `round_metadata:str?`(JSON text), `video:File?`, `audio:File?` | `SessionOut` **201** | `sessions` INSERT | **Inconsistent** — `async def` but performs blocking `file.file.read(262144)` in a `while` loop (sessions.py:112-120), stalling the event loop on every upload |
| `/api/sessions/json` | POST | Opt | `SessionCreate` JSON: `title`, `description?`, `round_type="jam"`, `overall_score:float?`, `round_metadata:dict`, `report:dict?`, `duration_seconds:float` | `SessionOut` 201 | `sessions` INSERT | Working. Accepts a client-supplied `overall_score` **and** `report` — a caller can forge its own score before any analysis exists |
| `/api/sessions/{id}` | GET | Opt | path `session_id:int` | `SessionDetailOut`: `SessionOut` + `transcription:{id,session_id,text,language,confidence,created_at}?` + `analysis:{id,session_id,speaking_pace,filler_words_count,filler_words_list:dict,clarity_score,eye_contact_percentage,posture_quality,created_at}?` + `feedback:[AIFeedbackOut]` + `audio_url:str?` | `sessions`,`transcriptions`,`session_analyses`,`ai_feedback` | **Inconsistent** — `SessionOut` serialises **`video_path` and `audio_path`, i.e. absolute server filesystem paths**, straight to the browser [V] |
| `/api/sessions/{id}/audio` | GET | Opt | path | `FileResponse` inline, `Cache-Control: private, max-age=3600` / **404** | `sessions` | Working [V-live 404 when no media]. Falls back to `video_path` via `session_media.get_session_audio_path` [V] |
| `/api/sessions/{id}` | PATCH | Opt | `SessionUpdate`: `title?`, `description?`, `status?`, `overall_score?`, `report?` | `SessionOut` | `sessions` UPDATE | **Inconsistent** — `status` is a free `str`; no enum, so `"complated"` persists. `report` is arbitrary JSON |
| `/api/sessions/{id}` | DELETE | Opt | path | **204** empty body | `sessions` + cascade | Working [V-live 204, then 404] |
| `/api/sessions/{id}/analyze` | POST | **None** | path only, no body | `SessionDetailOut` / **500** `{detail:"Analysis failed. Please try again."}` | writes `transcriptions`, `session_analyses`, `ai_feedback`, `sessions.{status,overall_score,round_metadata,report}` | **Inconsistent** — no auth; blocking; 11 downstream calls in one transaction |
| `/api/sessions/{id}/analysis` | GET | **None** | path | `SessionAnalysisOut` / **404** | read | Working |
| `/api/sessions/{id}/transcription` | GET | **None** | path | `TranscriptionOut` / **404** | read | **Unused** [V] |
| `/api/sessions/{id}/tts` | GET | **None** | path | `FileResponse` MP3 / **503** `{detail:"TTS synthesis currently unavailable"}` | read `sessions`,`ai_feedback`; writes `uploads/tts/` | **Unused** by the frontend [V]; **works** [V-live 200] |
| `/api/sessions/{id}/feedback` | GET | **None** | path | `List[AIFeedbackOut]` or **404** `{detail:"No feedback for session"}` | `ai_feedback` read | **Unused** — `api/feedback.ts#getFeedback` has zero call sites [V] |

`SessionOut` = `{id:int, title:str, description:str?, round_type:str, overall_score:float?, round_metadata:dict, report:dict?, user_id:int?, duration_seconds:float, video_path:str?, audio_path:str?, status:str, created_at:datetime}` **[V]** — frontend mirror `SessionSummary` in [types/index.ts:116](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/types/index.ts#L116) types `round_type`, `overall_score`, `round_metadata`, `report` as optional (`?`) though the backend always sends them, and omits `report`'s narrowing: it binds `report` to `VerbalIQReport` while the column is free JSON.

### 3.3 HR & Behavioral — `prefix="/api/hr"`, all `-> dict` (no `response_model`) **[V]**

| Endpoint | Method | Auth | Request (exact) | Response (exact keys) | Persistence | Status |
|---|---|---|---|---|---|---|
| `/api/hr/tracks` | GET | None | — | `{tracks:[{id:str, title:str, icon:str, desc:str, rubric_focus:str}]}` | read `hr_questions` | Working [V-live] |
| `/api/hr/questions` | GET | None | query `category:str?`, `difficulty:str?` | `{count:int, questions:[{id:str, track:str, text:str, difficulty:str, source_type:str, keywords:[str], rubric:{green_flags,red_flags,key_focus}}]}` | `hr_questions` | **Unused** [V]. Also **Inconsistent**: `track` carries title-cased DB `category` (`"Culture Fit"`) while `/tracks` ids are snake_case (`"culture_fit"`) [V-live] |
| `/api/hr/start` | POST | Req | `StartHRRequest` JSON: `role:str="Software Engineer"`, `target_company:str?`, `interview_mode:str="standard_hr"`, `max_questions:int 1..8 =4` | `{session_id:int, role, target_company:str?, interview_mode, current_question:dict?, question_count:0, max_questions:int, is_complete:false}` | `sessions` INSERT + `hr_interviews` INSERT | **Inconsistent** — `interview_mode="standard_hr"` matches **no** track id; the bank silently returns a Culture-Fit question [V-live] |
| `/api/hr/answer` | POST | Req | **multipart**: `session_id:int(req)`, `answer:str(req)`, `audio_file:File?` | `{session_id, evaluation:dict, next_question:dict?, is_complete:bool, report:dict?, question_count:int, max_questions:int, audio_url:str?, vocal_delivery:dict}` | `hr_interviews.questions` JSON append, `question_count`, `current_question`; on completion `sessions.{status,overall_score,report}` | **Inconsistent** — see §4.1 |
| `/api/hr/session/{id}` | GET | Req | path | start-shape + `questions:[…]`, `report`, `overall_score`, `created_at:str?` (ISO) | read | Working; no ownership check |
| `/api/hr/report/{id}` | GET | Req | path | `{session_id, role, target_company, interview_mode, overall_score, report, questions, created_at}` / **400** if no report | read | Working |
| `/api/hr/audio/{filename}` | GET | Req | path `filename` | `FileResponse` `audio/webm` / 404 | filesystem | Working |

`evaluation` keys (from `hr/evaluator.evaluate_hr_answer`) **[V]**: `overall_score`, `star_structure{situation{present:bool,summary:str}, task{…}, action{…}, result{…}, completeness_score:int, structure_critique:str}`, `personal_ownership_score`, `ownership_critique`, `specificity_score`, `specificity_critique`, `relevance_score`, `relevance_critique`, `coaching_feedback`, `ideal_star_script` — matches `HRAnswerEvaluation` in [api/hr.ts:18-29](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/hr.ts#L18) exactly.
`report` keys: `total_score`, `avg_ownership_score`, `avg_star_completeness`, `avg_specificity_score`, `strengths:[str]`, `weaknesses:[str]`, `executive_summary:str`, plus `vocal_delivery` injected by the route.

### 3.4 Guesstimate — `prefix="/api/guesstimate"` **[V]**

| Endpoint | Method | Auth | Request | Response | Persistence | Status |
|---|---|---|---|---|---|---|
| `/api/guesstimate/metadata` | GET | None | — | `{total_questions:int, categories:[{id,label,count}], difficulties:[…]}` | static JSON file | Working [V-live `990`] |
| `/api/guesstimate/random` | GET | None | query `category?`, `difficulty?` | `{question:str, category:str, difficulty:str}` | static | Working |
| `/api/guesstimate/start` | POST | Req | `StartGuesstimateRequest` JSON: `category:str="Market Sizing"`, `difficulty:str="Intermediate"`, `question:str?` (custom), `approach_type:str?="top_down"` | `{session_id, question, category, difficulty, approach_type, status:"in_progress"}` | `sessions` + `guesstimate_cases` | Working. Note: returns **`status`**, whereas HR/Technical return **`is_complete`** — no shared start contract |
| `/api/guesstimate/submit` | POST | Req | **multipart**: `session_id:int`, `answer:str`, `approach_type:str?="top_down"`, `audio_file:File?` | `{session_id, overall_score:float, evaluation:dict, audio_url:str?, vocal_delivery:dict}` | `guesstimate_cases.{candidate_answer,approach_type,audio_url,evaluation}`; `sessions.{status="completed",overall_score,report}` | **Inconsistent** — one-shot; a second submit **overwrites** the case and its score with no guard |
| `/api/guesstimate/session/{id}` | GET | Req | path | `{session_id, question, category, difficulty, approach_type, candidate_answer, audio_url, is_complete, overall_score, evaluation, created_at}` | read | Working |
| `/api/guesstimate/report/{id}` | GET | Req | path | same minus `is_complete` / **400** | read | Working |
| `/api/guesstimate/audio/{filename}` | GET | Req | path | `FileResponse` / 404 | filesystem | Working |

`evaluation` (success path, `guesstimate/evaluator.py:858-897`) **[V]**: `evaluation_version=2`, `overall_score:int`, `rubric_scores{mece_score,assumption_score,mental_math_score,sanity_check_score}`, flattened duplicates of all four + their `*_feedback` strings, `candidate_final_estimate`, `plausible_industry_range`, `candidate_estimate_structured{value,unit,period,geography,formatted_display}`, `plausible_range_structured{min,max,unit,period,geography,benchmark_source,formatted_display}`, `range_diagnostic{status,is_within_range,variance_percent,variance_reference,range_midpoint,unit_match,summary_label,diagnostic_note}`, `model_approach_name`, `model_breakdown_steps`, `candidate_branch_diagnostics`, `sensitivity_analysis{status,driver_name,formula_expression,baseline/low/high_*,impact_percent,conservative_scenario,aggressive_scenario,has_multi_driver_comparison,leverage_ratio,multi_driver_guidance,tornado_ranking,explanation}`, `scoring_weights{mece,assumption,math,sanity,rounding_policy,formula_display}`, `strengths`, `weaknesses`, `ideal_verbal_script`, `executive_summary`, plus route-injected `vocal_delivery` and `laya_metrics`.
**[V] The `default_fallback` returned when the LLM errors has a *different shape*** (no `rubric_scores`, pre-baked `sensitivity_analysis`/`range_diagnostic`) — so `GuesstimateEvaluation` is only valid on the happy path.

### 3.5 Technical — `prefix="/api/technical"` **[V]**

| Endpoint | Method | Auth | Request | Response | Persistence | Status |
|---|---|---|---|---|---|---|
| `/api/technical/resume/upload` | POST | Req | multipart `file:File` (**`.pdf` only**, 400 otherwise) | `{status:"success", message:str, resume_name:str}` | `users.resume_path/resume_name`; Chroma collection `user_{id}` | **Inconsistent** — indexing failure is swallowed (`logger.warning`), so the API returns **success even when the resume was never embedded** |
| `/api/technical/resume/status` | GET | Opt | — | `{has_resume:bool, resume_name:str?}` | read | Working |
| `/api/technical/resume` | DELETE | Req | — | `{status, message}` | `users` UPDATE | **Incomplete** — clears DB columns but never deletes the Chroma collection, so stale vectors keep grounding future questions |
| `/api/technical/start` | POST | Req | `StartInterviewRequest` JSON: `role:str="Full Stack Engineer"`, `target_company:str?`, `company_tier:str="tier1_product"`, `max_questions:int 1..10=5` | `{session_id, role, target_company, company_tier, current_question:{id,text,type}, question_count:0, max_questions, is_complete:false}` | `sessions` + `technical_interviews` | Working. `company_tier` is a free `str`; an unknown tier silently defaults |
| `/api/technical/answer` | POST | Req | **multipart**: `session_id:int`, `answer:str`, `audio_file:File?` | `{session_id, evaluation, next_question:dict?, is_complete, report:dict?, question_count, max_questions, audio_url, vocal_delivery}` | `technical_interviews.{questions,question_count,current_question}`; `sessions.{status,overall_score,report}` | **Inconsistent** — `evaluation` falls back to the literal `{"score":7,"feedback":"Good response."}` (technical.py:329) when the graph returns nothing |
| `/api/technical/session/{id}` | GET | Req | path | start-shape + `questions`, `report`, `overall_score` (**no `created_at`**, unlike HR/Guesstimate) | read | **Inconsistent** |
| `/api/technical/report/{id}` | GET | Req | path | `{session_id, role, target_company, company_tier, overall_score, report, questions, created_at}` / 400 | read | Working |
| `/api/technical/audio/{filename}` | GET | **None** | path | `FileResponse` / 404 | filesystem | **Inconsistent** — the only audio-serving endpoint with no auth dependency |

`evaluation` keys: `score:int 1-10`, `feedback`, `conciseness_score:1-10`, `rambling_detected:bool`, `rambling_critique`, `jargon_vs_understanding`, `applied_understanding_score:1-10`, `jargon_critique`, `star_breakdown{situation,task,action,result:bool, structure_feedback}`, `ideal_concise_script`, `conclusion_checkpoint_index`, `sentences:[{index,text,start,end,is_conclusion_checkpoint,is_rambling,highlight,rationale}]`. **[V] Per-answer scores are 1-10 here and 0-100 in every other module** — `progress.py` compensates with `* 10.0`.
`report` keys: `total_score`, `avg_conciseness_score`, `avg_understanding_score`, `rambling_rate_percent`, `strengths`, `weaknesses`, `summary`, + `vocal_delivery`.

### 3.6 Coach — `prefix="/api/coach"`, all `-> Dict[str,Any]` **[V]**

| Endpoint | Method | Auth | Request | Response | Status |
|---|---|---|---|---|---|
| `/api/coach/active-plan` | GET | Opt | — | `{has_plan:bool, plan:{id,target_role,roadmap_title,status,target_date,identified_bottlenecks,days,meta_summary,created_at,updated_at}\|null}` | Working |
| `/api/coach/generate-plan` | POST | Opt | `{target_role:str?="General Placement", target_date:str?, force_replan:bool?=false}` | `{has_plan, reused_existing:bool, plan:{…}}` | Working; runs a full LangGraph agent inside one request |
| `/api/coach/complete-day` | POST | Opt | `{plan_id:int, day_number:int, score_achieved:float?, notes:str?}` | `{success:true, plan:{id,status,days,completed_day}}` | **Inconsistent** — `notes` is accepted by `CompleteDayRequest` but **never persisted** (coach.py:199-216 ignores it) |
| `/api/coach/auto-sync` | POST | Opt | — | `{synced:bool, …}` or `{synced:false, message:str}` | Working |

### 3.7 Progress / Placement Readiness — `prefix="/api/progress"`, all `-> dict` **[V]**

| Endpoint | Response keys | Notes |
|---|---|---|
| `/api/progress/summary` | `total_sessions, completed_sessions, total_duration_seconds, avg_clarity_score, avg_speaking_pace, avg_eye_contact, avg_posture_quality, best_pace, best_clarity, total_filler_words` | [V-live] matches `ProgressSummary` exactly. Pace outliers filtered to 40-240 WPM; "best pace" = closest to **145 WPM** |
| `/api/progress/metrics` | `[{session_id,title,created_at,speaking_pace,clarity_score,filler_words_count,eye_contact_percentage,posture_quality}]` | matches `ProgressMetric` |
| `/api/progress/technical` | `{timeline:[{session_id,title,role,target_company,score,conciseness_score,rambling_rate,applied_understanding_score,rote_reliance_score,benchmark:85.0,competitive_threshold:70.0,questions_count,verdict,created_at}], summary:{total_drills,completed_drills,avg_score,peak_score,avg_conciseness,avg_rambling_rate,avg_applied_understanding,avg_rote_reliance,latest_verdict}, competencies:[{category,avg_score,challenges_count}]}` | matches `TechnicalProgressResponse` |
| `/api/progress/guesstimate` | `{timeline:[… structure_score,math_score,proxy_score,sanity_score,candidate_estimate,plausible_range,range_diagnostic,sensitivity_analysis,candidate_branch_diagnostics,model_breakdown_steps], summary:{…, is_single_attempt, weighting_metadata{mece:35,assumption:25,math:20,sanity:20,formula_display}, latest_diagnostics}, categories:[{category,avg_score,drills_count}]}` | matches |
| `/api/progress/hr` | `{timeline:[{session_id,title,role,target_company,mode,score,avg_ownership_score,avg_star_completeness,avg_specificity_score,verdict,created_at}], summary:{…}, competencies:[{track,avg_score,drills_count}]}` | matches |
| `/api/progress/placement-readiness` | `{cards:[4×{key,title,track_number,attempt_count,completed_count,latest_attempt_at,latest_session_id,status,primary_metric{label,value,unit},secondary_metrics:[…],drill_path,report_path}], attempted_count, ready_count, total_rounds:4, evaluation_rule}` | **Inconsistent** — see §4.2 |

Verdict thresholds per round **[V]**: Technical `85 Strong Hire / 70 Competitive Hire / 55 Lean Hire`; Guesstimate `85 MBB-Tier-1 Ready / 70 Competitive Consultant / 55 Promising Structure`; HR `85 Executive Leadership Ready / 70 Strong STAR Practitioner / <50 Needs Structural Rigor`; JAM via `analysis.py` bands 85/70/50.

---

## 4. Contract-mismatch register (REST)

### 4.1 Three `pick_next_hr_question` shapes, one field
`hr/question_bank.get_next_hr_question` returns `{id, track, text, difficulty, source_type, keywords, rubric}` (7 keys); the exhausted-bank emergency path in `hr_service.py:30-38` returns `{id, track, text, rubric}` (**4 keys**). `HRQuestionItem` in [api/hr.ts:31-42](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/hr.ts#L31) types `difficulty`/`source_type` as absent and `rubric` optional, so the UI survives — but any consumer reading `question.difficulty` breaks on the last question of a deep interview. **[V]**

### 4.2 `placement-readiness` `status` union is wrong **[V]**
Backend emits **4** values (`progress.py:631` adds `"developing"` for guesstimate when `len(guesstimate_completed) == 0`):
`"ready" | "in_progress" | "not_attempted" | "developing"`.
`PlacementReadinessCard.status` in [api/analysis.ts:275](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/analysis.ts#L275) declares only `'"ready" | "in_progress" | "not_attempted"'`. TypeScript therefore believes `"developing"` is impossible; any `switch`/record lookup keyed on the union has an unhandled branch at runtime while still compiling. Backend also emits `extended_metrics:{mental_math:str}` on the guesstimate card, which has **no field in the frontend interface at all**.

### 4.3 `null` vs `undefined` across all module DTOs **[V]**
Backend sends `"target_company": None` → JSON `null`. Frontend types say `target_company?: string` (absent ≠ null) in `api/hr.ts:58`, `api/technical.ts:97`, `types/index.ts` `SessionSummary.description: string | null` (correctly nullable there). The module DTOs are the wrong ones. Same for `current_question: HRQuestionItem | null` (correct) but `next_question?: HRQuestionItem` (backend sends explicit `null`). Type-checked only because `axios` returns `any` at the boundary and the generic is a cast, not a validation.

### 4.4 Per-answer `vocal_delivery` is sent and never read **[V]**
`/api/hr/answer`, `/api/technical/answer`, `/api/guesstimate/submit` all return a `vocal_delivery` object (a full audEERING result with `summary`/`dimensions`/`timeline`/`prosody`). No studio page destructures it; reports read `report.vocal_delivery` instead, which is populated from the Redis drain. Confirmed by grep — `vocal_delivery` appears only inside `api/*.ts` type declarations and `*Report.tsx` pages. Not a bug (the report path is authoritative), but it is **~2 KB of per-question payload on the hot submission path that no consumer reads**.

### 4.5 Frontend types the response, but nothing validates it **[V]**
`apiClient.get<T>()` is a compile-time assertion only. There is no `zod`/`io-ts`/runtime guard anywhere in `frontend/src`. If the backend renames `next_question` the frontend compiles and ships `undefined` into state. `getTechnicalSession()` is declared `Promise<any>` [api/technical.ts:147](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/technical.ts#L147) — the contract is deliberately unmodelled there.

### 4.6 Unused / orphaned endpoints **[V]**
Unused by the frontend: `GET /api/hr/questions`, `GET /api/sessions/{id}/feedback`, `GET /api/sessions/{id}/transcription`, `GET /api/sessions/{id}/tts`, `POST /api/sessions/json` (used only indirectly — nothing in `frontend/src` references `/sessions/json`), and all **11 `/api/jam/...` aliases**. `api/feedback.ts` is itself dead code (zero importers). `POST /api/sessions/json` accepting a client-supplied `overall_score` + `report` is both unused *and* the most abusable write path in the system.

### 4.7 `analyze_session` hard-codes UI copy into the API **[V]**
[analysis.py:262-270](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/analysis.py#L262) fabricates defaults when the LLM omits them: `congruence = {"status":"High Alignment","analysis":"Nonverbal delivery matched spoken messaging."}` and `avatar_reaction = {"expression":"empathic_nod","gesture":"open_palm_welcome","timing":"00:02"}`. These are persisted into `sessions.report` and rendered as if measured. Same class of issue as `prosody_confidence` default `84.0`, `vocal_energy_db` `-22.0`, `eye_contact_percentage` `82.0`, `posture_quality` `85.0` (analysis.py:248-254). See `ARCHITECTURE_RISKS.md` C-2.

### 4.8 Error shape is uniform but undocumented **[V]**
Every failure is FastAPI's default `{"detail": str}` — HTTP 400/401/403/404/409/413/500/503. `analyze_session` deliberately collapses all exceptions into `500 "Analysis failed. Please try again."` after logging the traceback (analysis.py:304-308), so the client cannot distinguish missing audio from dead LLM. Frontend reads `err.response.data.detail` (e.g. RecordingSession.tsx:69-74) — consistent. Pydantic 422 responses instead return `detail: [{loc, msg, type}]`, an **array**, which the `detail || message` fallback renders as `[object Object]` if ever surfaced.

---

## 5. Cross-cutting observations

- **[V] No idempotency or concurrency guard on any submission endpoint.** Two simultaneous `POST /api/hr/answer` calls for the same session both read `hr.current_question`, both append to `hr.questions`, and the second overwrites the first (`hr.questions = updated_questions`, hr.py:186-188) — a classic lost-update on a JSON column. `question_count` is then `len(questions)`, so one question silently disappears.
- **[V] Transaction boundaries.** `get_db` yields one session per request; `db.flush()` then a second INSERT then a single `db.commit()` occurs in all three `start` handlers (session + detail row), so those are atomic. But `/api/hr/answer` commits **after** the LLM call, meaning an LLM timeout leaves the audio file on disk and the DB untouched; `/api/technical/answer` calls `store_performance` (Mem0/Chroma) **after** `db.commit()` (technical.py:354-364 vs 364), so memory write failure cannot roll the DB back and vice versa. `analysis.py` sets `status="processing"`, commits, then runs 5 minute-scale model calls, then commits again — a crash between leaves the session permanently `processing`.
- **[V] `settings.max_upload_size_mb = 200`** is enforced only in `POST /api/sessions` (`_save_upload`). The HR/Technical/Guesstimate `audio_file` handlers write `await audio_file.read()` — **entire file, unbounded, into RAM** (hr.py:143, technical.py:262, guesstimate.py:139). No size check, no extension check, no MIME check on three of the four upload paths.
- **[V] Filename trust.** Technical/HR/Guesstimate build server filenames from `session.id` + `question_count` + `user.id`, discarding the client name — safe. But `resume/upload` uses `f"user_{current_user.id}_{file.filename}"` (technical.py:75) with only a `.pdf` suffix check; `file.filename` is client-controlled and, although the basename is later recovered through `Path(...).name`, the write itself is not sanitised for path separators on the initial join.
- **[V] No rate limiting, no request logging middleware, no correlation-id header, and no API versioning** (`/api/…`, not `/api/v1/…`) anywhere in `main.py`.
- **[V]** CORS is `allow_origins=[localhost:3000, localhost:5173, 127.0.0.1:5173]` with `allow_credentials=True`. No deployed origin is present, so a non-localhost frontend cannot call the API at all; `VITE_API_URL` is overridable but the server list is not env-driven.

---

## 6. Consolidated API contract table (all modules, consumer ↔ provider)

The matrices above are organised by *provider*. This table re-cuts the same surface by **module ownership and consumer**, using the exact column set the brief requested. `Consumer` is the traced caller in `frontend/src` (grep-verified `[V]`); `—` means **no caller exists in the repository**. Provider is always `backend/app/routes/<file>.py` inside the single FastAPI process `[V]`.

| Endpoint | Method | Module | Consumer | Provider | Request Schema | Response Schema | Authentication | Persistence | Status |
|---|---|---|---|---|---|---|---|---|---|
| `/api/auth/register` | POST | cross-module | `auth.ts#register` ← `LoginPage` | `auth.py#register` | `UserCreate{email,username,full_name?,password}` | `Token{access_token,token_type,user}` 201 | None (public) | `users` INSERT | Working |
| `/api/auth/login` | POST | cross-module | `auth.ts#login` ← `LoginPage` | `auth.py#login` | `UserLogin{email,password}` | `Token` / 401 | None (public) | read | Working |
| `/api/auth/me` | GET | cross-module | `auth.ts#getMe` ← `AuthContext.tsx` | `auth.py#me` | header `Bearer` | `UserOut` / 401 / 404 | **`Hdr` — the only strict check in the app** | read | Working |
| `/api/sessions` | GET | JAM | `sessions.ts#listSessions` ← `useSessions` / DashboardPage | `sessions.py#list_sessions` | query `limit,offset,round_type` (all defaulted) | `List[SessionOut]` | `Opt` → guest filter `user_id==1 OR IS NULL` | `sessions` read | **Inconsistent** |
| `/api/sessions` | POST | JAM | `sessions.ts#uploadSession` ← `RecordingSession.tsx` `handleUpload` | `sessions.py#create_session` | multipart `title,description?,duration_seconds,round_type,round_metadata?,video?,audio?` | `SessionOut` 201 | `Opt` | `sessions` INSERT + file | **Inconsistent** |
| `/api/sessions/json` | POST | JAM | **`—`** | `sessions.py#create_session_json` | `SessionCreate{…,overall_score?,report?}` | `SessionOut` 201 | `Opt` | `sessions` INSERT | **Unused** — yet live in data (rows 14/15/19) `[V-live]` |
| `/api/sessions/{id}` | GET | JAM | `sessions.ts#getSession` ← `useSessionDetail` / AnalysisPage | `sessions.py#get_session` | path | `SessionDetailOut` | `Opt` + `_get_session_for_user` | 4 tables read | **Inconsistent** (leaks `video_path`/`audio_path`) |
| `/api/sessions/{id}/audio` | GET | JAM | `SessionDetail.audio_url` → `<audio>` in `AnalysisResults.tsx:29` | `sessions.py#serve_audio` | path | `FileResponse` / 404 | `Opt` | filesystem | Working |
| `/api/sessions/{id}` | PATCH | JAM | **`—`** | `sessions.py#update_session` | `SessionUpdate{title?,description?,status?,overall_score?,report?}` | `SessionOut` | `Opt` | `sessions` UPDATE | **Unused** + free-string `status` |
| `/api/sessions/{id}` | DELETE | JAM | `sessions.ts#deleteSession` ← `useDeleteSession` | `sessions.py#delete_session` | path | **204** empty | `Opt` + ownership | `sessions` + 6 cascades | Working (media file orphaned) |
| `/api/sessions/{id}/analyze` | POST | JAM | `sessions.ts#analyzeSession` ← `useAnalyzeSession`, `RecordingSession`, `AnalysisPage` | `analysis.py#analyze_session` | path only, **no body** | `SessionDetailOut` / 500 | **None** | `transcriptions`,`session_analyses`,`ai_feedback`,`sessions` | **Inconsistent** (C-02) |
| `/api/sessions/{id}/analysis` | GET | JAM | **`—`** | `analysis.py#get_analysis` | path | `SessionAnalysisOut` / 404 | **None** | read | **Unused** |
| `/api/sessions/{id}/transcription` | GET | JAM | **`—`** (transcript ships inside `SessionDetailOut`) | `analysis.py#get_transcription` | path | `TranscriptionOut` / 404 | **None** | read | **Unused** |
| `/api/sessions/{id}/tts` | GET | JAM | **`—`** | `analysis.py#tts` | path | MP3 `FileResponse` / 503 | **None** | reads `ai_feedback`, writes `uploads/tts/` | **Unused** (works `[V-live]`) |
| `/api/sessions/{id}/feedback` | GET | JAM | `feedback.ts#getFeedback` — **zero call sites** | `feedback.py#list_feedback` | path | `List[AIFeedbackOut]` / 404 | **None** | `ai_feedback` read | **Unused** |
| `/api/jam/api/sessions/**` | ×9 | JAM | **`—`** — no frontend file references the prefix | re-mounted `sessions.py` + `analysis.py` | identical | identical | identical | identical | **Inconsistent / Unused** — 11 aliases; the `/feedback` alias **404s** `[V-live]` |
| `/api/hr/tracks` | GET | HR | `hr.ts#getHRTracks` ← `HRStudio.tsx:63` | `hr.py#tracks` | — | `{tracks:[{id,title,icon,desc,rubric_focus}]}` | **None** | `hr_questions` read | Working |
| `/api/hr/questions` | GET | HR | **`—`** | `hr.py#questions` | query `category?,difficulty?` | `{count,questions[]}` | **None** | `hr_questions` read | **Unused** + `track` casing divergence (§4.6, `[V-live]`) |
| `/api/hr/start` | POST | HR | `hr.ts#startHRInterview` ← `HRStudio.tsx:197` | `hr.py#start` | `StartHRRequest{role,target_company?,interview_mode,max_questions}` | `{session_id,role,target_company,interview_mode,current_question,question_count,max_questions,is_complete}` | `Req` (non-rejecting, C-01) | `sessions` + `hr_interviews` INSERT | **Inconsistent** (H-06) |
| `/api/hr/answer` | POST | HR | `hr.ts#submitHRAnswer` ← `HRStudio.tsx:243` | `hr.py#answer` | multipart **Form** `session_id:int,answer:str` + `audio_file:File?` | `{session_id,evaluation,next_question?,is_complete,report?,question_count,max_questions,audio_url?,vocal_delivery}` | `Req`, **no ownership check** (C-03) | `hr_interviews.questions` RMW; on last → `sessions` | **Inconsistent** (C-07, H-04, H-07) |
| `/api/hr/session/{id}` | GET | HR | restore effect `HRStudio.tsx:74` | `hr.py#session_state` | path | start-shape + `questions,report,overall_score,created_at` | `Req`, no ownership | read | Working (unauthorized) |
| `/api/hr/report/{id}` | GET | HR | `hr.ts#getHRReport` ← `HRReport.tsx:19` | `hr.py#report` | path | `{session_id,role,target_company,interview_mode,overall_score,report,questions,created_at}` / 400 | `Req`, no ownership | read | Working |
| `/api/hr/audio/{filename}` | GET | HR | `q.audio_url` absolute URL → `<audio>` in `HRReport.tsx` | `hr.py#serve_audio` | path | `FileResponse audio/webm` / 404 | `Req` ✔ | filesystem | Working |
| `/api/guesstimate/metadata` | GET | Guesstimate | `getGuesstimateMetadata` ← `GuesstimateStudio.tsx:110` | `guesstimate.py#metadata` | — | `{total_questions,categories[],difficulties[]}` | **None** | static JSON | Working `[V-live 990]` |
| `/api/guesstimate/random` | GET | Guesstimate | `getRandomGuesstimate` ← `GuesstimateStudio.tsx:117` | `guesstimate.py#random` | query `category?,difficulty?` | `{question,category,difficulty}` | **None** | static | Working |
| `/api/guesstimate/start` | POST | Guesstimate | `startGuesstimateInterview` ← `GuesstimateStudio.tsx:268` | `guesstimate.py#start` | `{category,difficulty,question?,approach_type?}` | `{session_id,question,category,difficulty,approach_type,status}` | `Req`, no ownership | `sessions` + `guesstimate_cases` | **Inconsistent** (G-2: `status` not `is_complete`) |
| `/api/guesstimate/submit` | POST | Guesstimate | `submitGuesstimateAnswer` ← `GuesstimateStudio.tsx:311` | `guesstimate.py#submit` | multipart Form `session_id,answer,approach_type?,audio_file?` | `{session_id,overall_score,evaluation,audio_url?,vocal_delivery}` | `Req`, no ownership | `guesstimate_cases` **and** `sessions.report` (dual write, G-10) | **Inconsistent** (no idempotency; overwrites) |
| `/api/guesstimate/session/{id}` | GET | Guesstimate | restore effect `GuesstimateStudio.tsx:130` | `guesstimate.py#session_state` | path | `{…,is_complete,overall_score,evaluation,created_at}` | `Req`, no ownership | read | Working |
| `/api/guesstimate/report/{id}` | GET | Guesstimate | `getGuesstimateReport` ← `GuesstimateReport.tsx:18` | `guesstimate.py#report` | path | session-shape minus `is_complete` / 400 | `Req`, no ownership | read | Working |
| `/api/guesstimate/audio/{filename}` | GET | Guesstimate | `data.audio_url` → `<audio>` `GuesstimateReport.tsx:506` | `guesstimate.py#serve_audio` | path | `FileResponse` / 404 | `Req` ✔ | filesystem | Working |
| `/api/technical/resume/upload` | POST | Technical | `uploadResume` ← `TechnicalStudio.tsx` | `technical.py#resume_upload` | multipart `file:File` (`.pdf` only) | `{status:"success",message,resume_name}` | `Req` | `users.resume_*` + Chroma `user_{id}` | **Inconsistent** (H-11) |
| `/api/technical/resume/status` | GET | Technical | `getResumeStatus` ← `TechnicalStudio.tsx:102` | `technical.py#resume_status` | — | `{has_resume,resume_name?}` | `Opt` (true guest) | read | Working |
| `/api/technical/resume` | DELETE | Technical | `deleteResume` | `technical.py#resume_delete` | — | `{status,message}` | `Req` | `users` UPDATE | **Incomplete** (H-12) |
| `/api/technical/start` | POST | Technical | `startTechnicalInterview` ← `TechnicalStudio.tsx:293` | `technical.py#start` | `StartInterviewRequest{role,target_company?,company_tier,max_questions}` | `{session_id,role,target_company,company_tier,current_question,question_count,max_questions,is_complete}` | `Req`, no ownership | `sessions` + `technical_interviews` | Working |
| `/api/technical/answer` | POST | Technical | `submitTechnicalAnswer` ← `TechnicalStudio.tsx:334` | `technical.py#answer` | multipart Form `session_id,answer,audio_file?` | `{session_id,evaluation,next_question?,is_complete,report?,question_count,max_questions,audio_url,vocal_delivery}` | `Req`, no ownership | `technical_interviews` RMW; `sessions` | **Inconsistent** (C-07, H-08, H-13) |
| `/api/technical/session/{id}` | GET | Technical | restore effect `TechnicalStudio.tsx:124` | `technical.py#session_state` | path | start-shape + `questions,report,overall_score` — **no `created_at`** | `Req`, no ownership | read | **Inconsistent** (T-10) |
| `/api/technical/report/{id}` | GET | Technical | `getTechnicalReport` ← `TechnicalReport.tsx:22` | `technical.py#report` | path | `{session_id,role,target_company,company_tier,overall_score,report,questions,created_at}` / 400 | `Req`, no ownership | read | **Inconsistent** (T-06: two live report shapes) |
| `/api/technical/audio/{filename}` | GET | Technical | `q.audio_url` → `<audio>` `TechnicalReport.tsx:491` | `technical.py#serve_audio` | path | `FileResponse` / 404 | **None** ✗ (C-04) | filesystem | **Inconsistent** |
| `/api/coach/active-plan` | GET | Coach | `getActiveCurriculumPlan` ← `CurriculumCoachCard.tsx:32` | `coach.py#active_plan` | — | `{has_plan,plan}` | `Opt` + `_resolve_user_id(None)→1` | `curriculum_plans` read | Working |
| `/api/coach/generate-plan` | POST | Coach | `generateCurriculumPlan` ← `CurriculumCoachCard.tsx:59` | `coach.py#generate_plan` | `{target_role?,target_date?,force_replan?}` | `{has_plan,reused_existing,plan}` | `Opt` + **`user_id != 1` bypass** (C-05) | `curriculum_plans` INSERT/UPDATE | **Inconsistent** (dual-active plan risk, DB-12) |
| `/api/coach/complete-day` | POST | Coach | `completeCurriculumDay` ← `CurriculumCoachCard.tsx:80` | `coach.py#complete_day` | `{plan_id,day_number,score_achieved?,notes?}` | `{success,plan}` | `Opt` + bypass | `days` JSON + `flag_modified` | **Inconsistent** (`notes` discarded, P-8) |
| `/api/coach/auto-sync` | POST | Coach | `autoSyncCurriculumDrills` ← `CurriculumCoachCard.tsx:96` (button `:235`) | `coach.py#auto_sync` | — | `{synced,completed_day?,score_achieved?,message?}` | `Opt` + bypass | `days` + `sessions` read | Working (no idempotency key) |
| `/api/progress/summary` | GET | cross-module | `useProgressSummary` ← DashboardPage | `progress.py#summary` | — | `ProgressSummary` (9 keys) | `Opt` → `user_id==1 OR IS NULL` | `sessions`+`session_analyses` | Working |
| `/api/progress/metrics` | GET | cross-module | `useProgressMetrics` | `progress.py#metrics` | — | `[{session_id,title,created_at,speaking_pace,clarity_score,filler_words_count,eye_contact_percentage,posture_quality}]` | `Opt` | read | Working |
| `/api/progress/technical` | GET | Technical | `getTechnicalProgress` | `progress.py#technical` | — | `{timeline,summary,competencies}` | `Opt` | `technical_interviews` | **Inconsistent** (`score*10.0` scale fix, M-20) |
| `/api/progress/guesstimate` | GET | Guesstimate | `getGuesstimateProgress` | `progress.py#guesstimate` | — | `{timeline,summary{…,weighting_metadata},categories}` | `Opt` | `guesstimate_cases` | Working |
| `/api/progress/hr` | GET | HR | `getHRProgress` | `progress.py#hr` | — | `{timeline,summary,competencies}` | `Opt` | `hr_interviews` | Working |
| `/api/progress/placement-readiness` | GET | cross-module | `getPlacementReadiness` ← `DashboardPage:107` → `PlacementReadinessMatrix` | `progress.py#placement_readiness` | — | `{cards[4]{key,title,track_number,attempt_count,completed_count,latest_attempt_at,latest_session_id,status,primary_metric,secondary_metrics[],drill_path,report_path},attempted_count,ready_count,total_rounds,evaluation_rule,extended_metrics}` | `Opt` | all 4 detail tables | **Inconsistent** (**C-11**, P-2, P-3, M-19) |
| `/ws/session/{id}/emotion` | **WS** | cross-module (all four rounds) | `useLiveEmotionStream` ← `RecordingSession:22`, `HRStudio:60`, `GuesstimateStudio:103`, `TechnicalStudio:99` | `emotion_stream.py#emotion_websocket` | binary PCM s16le 16 kHz mono, 3200 B frames; text `{type:"context",category,question,partialTranscript}` or the verbs `close`/`stop`/`end` | telemetry frame (**no `type`**), `coach_nudge` tier 1, `coach_nudge` tier 2, `clear_nudge` | **None** — `accept()` is the first statement (H-02) | Redis `emotion:session:{id}` + process-local `_LAYAS` | **Inconsistent** (**C-06**, M-01…M-07) |

**Status tally for this table `[V]`:** 41 REST rows → **23 Working**, **14 Inconsistent**, **3 Unused**, **1 Incomplete**; plus 1 WebSocket, classified Inconsistent. The 11 `/api/jam` alias operations are counted as one row here and are **additionally** entirely unused by every frontend file.

**Reconciliation with §3.** §3 classifies by *provider behaviour* and so marks `/api/sessions/json` Working-with-a-caveat and `/api/sessions/{id}` PATCH Inconsistent; §6 classifies by *traced consumer*, so both become Unused. **This table is the authoritative contract tally**, since an endpoint with no caller cannot be verified from the consumer side at all. `[V]`

**Consumer-side observation `[V]`:** 9 of the 41 REST contracts have **zero callers** in the frontend — `/sessions/json`, `/sessions/{id}/analysis`, `/sessions/{id}/transcription`, `/sessions/{id}/tts`, `/sessions/{id}/feedback`, `/sessions/{id}` PATCH, `/hr/questions`, and the `/api/jam/**` family. These are precisely the endpoints most likely to drift unnoticed, and `/hr/questions` already has (the `track` casing divergence in §4.6, `[V-live]`).
