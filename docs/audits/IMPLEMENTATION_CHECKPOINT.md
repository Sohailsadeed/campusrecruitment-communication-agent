# SpeakFlow — Implementation Checkpoint

**Branch:** `feature/hr-round` · **Commit at start of this work:** `326d75e` (no commit created — implementation is deliberately left in the working tree)
**Checkpoint written:** 2026-10-31
**Task completed:** **AUTH-A** (contract Rev. 4, approved) — audit finding **C-01** only.
**Tasks NOT started:** AUTH-C (ownership), AUTH-D (analysis/feedback), AUTH-F (WebSocket handshake).
*(Updated 2026-11-01: AUTH-E is implemented with its browser pass outstanding — §11; AUTH-B / C-05 is implemented and verified — §12.)*

---

## 1. Root cause addressed

`get_current_user()` in [backend/app/routes/auth.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/auth.py) was fail-**open**. It had three non-rejecting paths:

1. No `Authorization` header (or a non-`bearer` scheme) → fell through to the fallback branch.
2. A present-but-invalid / expired / unverifiable JWT, or a valid JWT whose `sub` matched no row → same fall-through.
3. The fallback selected `order_by(User.id.asc())` — the **lowest-id user in the table** — and, if the table was empty, **created** `developer@verbaliq.local` with password `verbaliq123` and committed it.

Every one of the 16 handlers that depend on this resolver therefore received a real, authenticated-looking `User` for an unauthenticated request. C-01's "nominal auth layer" claim is the direct consequence; the four routes that skip the dependency entirely (C-02/C-03/C-04) and the `user_id != 1` clause (C-05) are **separate root causes, untouched here.**

## 2. Files changed by AUTH-A

| File | Change |
|---|---|
| [backend/app/routes/auth.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/auth.py) | **Modified — the only production-code change.** `get_current_user()` rewritten fail-closed; new module-level `_UNAUTHENTICATED_DETAIL`, `_WWW_AUTHENTICATE`, and `_unauthenticated()` factory. `git diff --stat`: 31 insertions, 20 deletions. |
| [backend/requirements-dev.txt](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/requirements-dev.txt) | **Created.** `pytest==8.3.4` only; comment records that `pytest-asyncio` is intentionally absent because every AUTH-A test is synchronous. Production `requirements.txt` untouched. |
| [backend/tests/conftest.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/conftest.py) | **Created.** Isolation envelope + `db_session` / `probe_app` / `register_user` fixtures. |
| [backend/tests/test_auth_fail_closed.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_auth_fail_closed.py) | **Created.** Tier-2 behavioural tests against a stubbed app. |
| [backend/tests/test_authz_guard_static.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_authz_guard_static.py) | **Created.** Tier-1 pure-AST guards (imports nothing from the app, opens no database). |

Unchanged and deliberately so: `get_optional_current_user()` (still returns `None` for guests), `hash_password`, `create_access_token`, `decode_token` (still the narrow `except JWTError`), `/register`, `/login`, `/me`, and every consumer route.

## 3. Contract change (AUTH-A)

**Behaviour now:**

| Request | Before | Now |
|---|---|---|
| Valid bearer token resolving to a user row | `User` | `User` (unchanged) |
| Missing `Authorization` | lowest-id user, or auto-created dev user | **401** |
| Non-`bearer` scheme (`Basic …`), `Bearer` without space | same fallback | **401** |
| `Bearer ` with empty/whitespace token | same fallback | **401** |
| Malformed, expired, or foreign-signed JWT | same fallback | **401** |
| Valid JWT, `sub` matches no user | same fallback | **401** |
| Empty `users` table | **writes a new user** | **401, zero writes** |
| DB error inside the resolver | masked as a fallback | **propagates as 500** — operational faults are never reclassified as authentication faults |

**Error shape** (uniform across every rejection, verified by test): `401`, body `{"detail": "Could not validate credentials"}`, header `WWW-Authenticate: Bearer`. A **fresh `HTTPException` is constructed per failure** — no shared module-level instance (a singleton would carry another request's traceback).

**Deliberately unchanged:** the resolver still reads `Header(default=None)` manually rather than using `fastapi.security.HTTPBearer`. That keeps the OpenAPI `securitySchemes` byte-identical and avoids HTTPBearer's 403-instead-of-401 path. Reverting this is a visible, single-line decision for whoever wants the schema to advertise bearer auth.

**No DB or protocol migration. No request/response schema change.** Only the set of responses a client can observe for an unauthenticated call changed (was: success; now: 401).

## 4. Frontend consumers

`tsc -b` (`npm run lint`) passes with **0 errors**. No frontend file was modified by AUTH-A.

The audit's frontend path is unaffected in the normal case: every route is behind `ProtectedRoute`, and `AuthContext` sends a bearer token via the `apiClient` interceptor, so a signed-in user keeps working. The two consumers that *were* silently relying on the fallback are:

- **Guesstimate live-context** and other module calls made before a token exists — they now receive 401 instead of a phantom user.
- **The HR/Guesstimate audio routes** (`serve_hr_audio`, `serve_guesstimate_audio`) — they are `<audio src>` **media-element** requests, which cannot send an `Authorization` header. Their static guard is in place (see §6) and they remain authenticated exactly as before AUTH-A; the fix for them is **AUTH-E**, not a weakening of their boundary (Decision B).

## 5. Tests executed and actual results

Isolated environment (speakvenv **not** modified — see §7):

```
cd backend && PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="C:/Users/Sohail/.venvs/speakflow-testdeps" \
  speakvenv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider \
  --basetemp="C:/Users/Sohail/.venvs/tmp-run"
```

**Result: `41 passed, 21 warnings in 1.73s`. 0 failed, 0 skipped.** No test was deselected or edited to pass; the one earlier failure was a mis-scoped assertion in my own static test (it looked for the `WWW-Authenticate` literal inside `_unauthenticated`'s AST while the literal lives in the module constant) and was corrected to assert the constant at module scope *and* that the helper reads it.

Warnings, all pre-existing and out of AUTH-A scope: `app/services/technical/rag.py:8` langchain-community sunset; `datetime.utcnow()` deprecation at `jose/jwt.py:311` and [backend/app/routes/auth.py:30](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/auth.py#L30) (the last is `create_access_token`, which AUTH-A did not touch).

**Coverage of the tiers:**

- **Tier 1 (static, zero imports):** `get_current_user` constructs no `User`; calls no `add/commit/flush/refresh`; every `raise` is a bare `_unauthenticated()` with no args or keywords (uniformity is structural, not incidental); the helper builds a fresh `HTTPException` and reads the module bearer constant; `get_optional_current_user` still returns `None`; the 16 bound handlers still number 5/5/6 in hr/guesstimate/technical; the two media-element audio routes are still bound to `get_current_user`; `stream_technical_audio`, `analysis.py` and `feedback.py` are asserted **still unbound** — these are tripwires that keep AUTH-C/D/E from being silently "fixed" by an unrelated edit.
- **Tier 2 (behavioural, stubbed):** 10 parametrised rejection headers → 401 + exact detail + exact `WWW-Authenticate`; valid token returns the user; unknown subject → 401 with `db.writes == 0`; empty users table → 401 with `db.writes == 0` and a `SELECT count(*) == 0` assertion afterwards; a `RuntimeError` from the session **propagates** rather than becoming 401; `decode_token`'s `except` stays narrow; route-level uniformity; a registered token → 200; `/register` 201, `/login` 200, `/me` 401 headerless and 200 with token (public endpoints still reachable); no `developer@verbaliq.local` or `verbaliq123` string remains anywhere under `backend/app`.

**Not executed:** no browser, no live server, no LLM/Whisper/Redis/Chroma call. The test design guarantees this — nothing imports `main`, so `create_all`, `check_and_apply_migrations()`, the HR seed, the log handlers and the model warm-up never run, and no handler body that would reach an external service is registered on the probe app.

## 6. Working-tree preservation (verified, this is a stop condition)

`git status --porcelain` after all work: **15 ` M` + 5 `??` = 20 entries.**

- The 14 pre-existing modified files are **all still present and unmodified by me** — the 15th ` M` is `backend/app/routes/auth.py`, AUTH-A's own change.
- Pre-existing untracked paths intact: `backend/app/services/audio_pcm.py`, `frontend/public/`, `docs/`.
- New untracked paths, both created by this approved task: `backend/requirements-dev.txt`, `backend/tests/`.
- **`backend/speakflow.db` sha256 unchanged:** `243ccb29e8cb419ae83a4e0650a762fa3aa7177c5932b4342254c72d8c65d864`, byte-identical to the pre-run baseline recorded in `/tmp/db-before.txt`.
- No `__pycache__` under `backend/tests/`, no `.pytest_cache` anywhere in the workspace, and `find backend -name "*.pyc" -newer backend/app/routes/auth.py` → **0** — every existing `.pyc` predates this session (`PYTHONDONTWRITEBYTECODE=1` was set for the run).
- `frontend/tsconfig.tsbuildinfo` was rewritten by `npm run lint` (mtime 23:56, 2258 bytes). It is gitignored (`.gitignore:13 *.tsbuildinfo`) and is the project's own build artifact, produced by the sanctioned lint command.
- `backend/speakvenv`: **unmodified.** `pip freeze` before and after staging compared — identical, 0 differences. Only `iniconfig`, `pluggy` and `pytest` were needed, and they were staged **outside** the workspace at `C:/Users/Sohail/.venvs/speakflow-testdeps`; the overlap audit reported `WOULD SHADOW: NONE` (all app deps — fastapi 0.147.0, sqlalchemy 2.1.5, httpx 0.28.1, pydantic 2.14.1, starlette 1.9.0, jose 3.3.0, passlib 1.7.4, packaging 26.3, colorama 0.4.6 — still resolve inside speakvenv).

## 7. Approved side-actions completed in this session

1. **Docs-only pass 1** — `.env`/Postgres caveat corrected in `AUDIT_SUMMARY.md` (§7 caveat 1) and `DATABASE_SESSION_AUDIT.md` (§9 caveat 1, incl. `config.py:14` → **`config.py:25`**). The original claim ".env defines no DATABASE_URL" was **false**; `.env` sets a PostgreSQL URL and `backend/app/database/engine.py:27-40` silently falls back to SQLite. SQLite observations are now labelled local-machine evidence; Postgres state is `[U]`. `.env` itself was not modified.
2. **Docs-only pass 2** — four over-certain Postgres cascade assertions corrected: `ARCHITECTURE_RISKS.md:385` (M-13), `DATABASE_SESSION_AUDIT.md:118`, `DATABASE_SESSION_AUDIT.md:365` (DB-02), `AUDIT_SUMMARY.md:145` (roadmap item 15). Each now separates verified DDL `[V]` and observed SQLite cascade `[V-live]` from the Postgres failure, which is inference `[I]` `[U]` and **was never tested**.
3. **Orphan cleanup** — deleted `backend/uploads/tts/session_23_coach.mp3` only, after re-verifying it was the file my own audit probe created (35 424 bytes, sha256 `9235d9be…25ce51`, mtime 2026-10-31 22:04:53) and that session 23 has no row (`sessions` uses plain `INTEGER PRIMARY KEY`, so the evidence is the id gap 4–22 with no session created on 2026-10-31). `session_7_coach.mp3` and `session_8_coach.mp3` — whose sessions exist — untouched. No other recording was deleted.

## 8. Caveats on this checkpoint

- **Browser Network-panel confirmation of the audio-URL routing was NOT performed.** T0-C was skipped by instruction; the sequencing decision rests on T0-A/T0-B.
- **AUTH-E was not required before AUTH-A** on the evidence gathered: `backend/uploads/` contains no `hr_audio`, `guesstimate_audio` or `technical_audio` directory at all (no such recording has ever existed on this host), there is no Vite `server.proxy`, and no FastAPI `StaticFiles` mount — so the root-relative `audio_url` never reaches :8000 regardless of auth. This is a *routing* observation, not a proof that no browser in another deployment would behave differently.
- **The user never asked me to run the backend, and I did not.** All §5 results come from the stubbed probe app; no live endpoint was exercised under AUTH-A.

## 9. Outstanding issues

1. **AUTH-A makes guest-mode calls 401 where they previously succeeded as a phantom user.** That is the intent, but it is a behaviour change for anyone running the studio drill UI without registering. If guest mode is a legitimate workflow, it needs an explicit, opt-in mechanism (a settings flag defaulting to `False`) — that is a contract decision, not an AUTH-A amendment.
2. **`POST /api/auth/register` is unauthenticated and ungated.** On a fresh datastore, the first caller to register owns the instance. Pre-existing; surfaced by removing the fallback, not introduced by it.
3. **`get_current_user` is duplicated in spirit by three other resolvers** (`get_optional_current_user`, `_get_optional_user` in the module routers) — 1 and 17 dependents respectively. Converging them is AUTH-C's scope.
4. **`datetime.utcnow()` deprecation** in `create_access_token` ([backend/app/routes/auth.py:30](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/auth.py#L30)) — hygiene, unrelated to C-01.
5. **C-02/C-03/C-04 are still live.** Four endpoints bypass identity entirely (`/analyze`, `/api/technical/audio/{filename}`, HR + Technical `/answer` resolve-and-discard). Removing the fallback makes C-01's blast radius smaller but does not close those doors.
6. **The `WWW-Authenticate` header is now the only challenge mechanism** — no `securitySchemes` were added to OpenAPI by design; generated clients still won't know to send a bearer token.

## 10. Next task

**AUTH-E** (task #9) — audio route authorization: fetch recordings through `apiClient` with Bearer auth and play them via Blob/Object URLs, so the HR and Guesstimate audio endpoints keep their authenticated boundary (Decision B) instead of being downgraded to optional auth. Per the agreed sequence **A → E → B → C → D → F**, AUTH-E is next and is **not** started; it requires its own contract and its own approval. No file belonging to AUTH-E was read-and-edited here; the static guards in `test_authz_guard_static.py` exist to make any accidental drift visible.

*(Superseded on 2026-11-01 — AUTH-E went through contract Rev. 3 → Rev. 10, was approved for implementation, and is now complete. See §11.)*

## 11. AUTH-E — audio route authorization + frontend playback (implemented 2026-11-01)

**Branch:** `feature/hr-round`  **HEAD:** `326d75e5e3c72f930ae39adb2ab3c4e634b0b392` — AUTH-E is **uncommitted**, as no commit was requested.
**Contract:** Rev. 10, approved with two mandatory implementation conditions. **Task:** #9.

### 11.1 Root cause

Two distinct defects, shipped as one fix because neither is usable without the other.

1. **Missing authorization, not missing authentication.** Both audio handlers received `current_user` and discarded it: the path was built from `Path(filename).name` and served if it merely existed. Any signed-in user could read any candidate's recording by naming its file — the filename is guessable from the public report payload, so `session_<id>_hr_q_<n>_<uid>.webm` was an IDOR surface. The database was never consulted.
2. **Frontend could not authenticate a media element.** `<audio src="/api/hr/audio/…">` is a root-relative URL that, on the `npm run dev` origin (:5173), never reaches the backend on :8000 at all; and a media-element fetch cannot carry an `Authorization` header, so even a routed request would have been a credential-less 401.

### 11.2 Files changed by AUTH-E (exact scope — 8 paths, all approved)

| Path | Change |
|---|---|
| [backend/app/services/audio_ownership.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/services/audio_ownership.py) | **new leaf**, 238 lines — the five-stage decision, no DB writes |
| [backend/app/routes/hr.py:289](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/hr.py#L289) | handler body → `audio_file_response(resolve_hr_audio_path(db, current_user, filename))`; `get_db` bound; `pathlib` import dropped |
| [backend/app/routes/guesstimate.py:260](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/guesstimate.py#L260) | same shape for the guesstimate route |
| [backend/tests/audio_fixtures.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/audio_fixtures.py) | **new** — stub app with only the two routers, accounts, sessions, clip writer, autouse clip cleaner. Never imports `main` |
| [backend/tests/test_audio_ownership.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_audio_ownership.py) | **new** — 43 test functions (142 cases after parametrization) |
| [frontend/src/api/audioBlob.ts](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/audioBlob.ts) | **new**, 225 lines — destination guard, authenticated blob fetch, pure lifecycle helpers, `createClipStore`. No DOM, no React |
| [frontend/src/components/Recording/ProtectedAudioPlayer.tsx](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Recording/ProtectedAudioPlayer.tsx) | **new**, 173 lines — the shared player |
| [frontend/src/pages/hr/HRReport.tsx:338](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/pages/hr/HRReport.tsx#L338) · [frontend/src/pages/guesstimate/GuesstimateReport.tsx:509](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/pages/guesstimate/GuesstimateReport.tsx#L509) | one line each: `<audio controls src=…>` → `<ProtectedAudioPlayer audioUrl=… className=…>`; `print:hidden` wrappers untouched |

Unchanged by design: `frontend/src/api/client.ts` (not in scope), `api/hr.ts` / `api/guesstimate.ts` types, every AUTH-A artefact, `AnalysisResults.tsx` (JAM's session-audio route is deliberately not migrated), no schema, no migration, no dependency, no `speakvenv` change.

### 11.3 Behaviour change

**Backend** — a request is served only after five stages, each of which denies with the *same* 404 body as the pre-existing missing-file case (`"Audio recording file not found."`), so denial is indistinguishable from absence: (1) raw-string grammar `fullmatch` before any path work, canonical-integer round-trip and full-filename reconstruction; (2) ownership — filename uid == caller, `session.user_id` == caller, NULL-orphan denied, and the requested route must be one the stored `audio_url` actually points at; (3) `resolve()` + `is_relative_to(upload_dir)` confinement; (4) `is_file() ∧ st_size > 0 ∧ os.access(R_OK)`; (5) `FileResponse(media_type="audio/webm")` with `Cache-Control: private, no-store` and **no** `Content-Disposition` (the old `filename=` header invited a download, which is how a recording leaves the browser). Range/206/416 is Starlette's own, unchanged.

**Frontend** — the clip string read from the database is validated before a token is attached to it (only a root-relative `/api/…` path is ever passed to `apiClient`; a legacy absolute URL must match a configured origin and is re-homed to its pathname). Playback is an authenticated `responseType: "blob"` fetch into an object URL. Attempt/status identity lives in a per-instance store read with `useSyncExternalStore`, so a resource release and the retraction of its claim happen in one synchronous step; installation is sequential and fail-fast, rollback is best-effort and reports every failed step, and a rejected `publishReady()` fails the transaction rather than reporting success.

### 11.4 Tests executed — actual results

Backend, from `backend/`, pytest staged outside the repo at `C:/Users/Sohail/.venvs/speakflow-testdeps` (speakvenv has none):

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="C:/Users/Sohail/.venvs/speakflow-testdeps" \
  speakvenv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider \
  --basetemp="C:/Users/Sohail/.venvs/pytest-base-authE"
```

| Run | Result |
|---|---|
| **RED** — tests only, service not yet written | `115 failed, 67 passed, 1 skipped` — the failures were `assert 200 == 404` on foreign-clip, IDOR, orphan and traversal cases, i.e. the suite demonstrated the live vulnerability rather than an import error |
| **GREEN** — full suite | **`182 passed, 1 skipped`** in 14.23s |
| AUTH-E file alone | `141 passed, 1 skipped` |
| AUTH-A subset (`test_auth_fail_closed.py`, `test_authz_guard_static.py`) | **`41 passed`** — unchanged |

The single skip is `test_audio_ownership.py:438`, the **file**-symlink case: unprivileged Windows returns `WinError 1314`. The **directory**-escape case runs for real via `_winapi.CreateJunction` and asserts both the denial and that the junction genuinely escaped the upload root, so the confinement test is earned, not decorative.

Frontend — out-of-repo Node 24 harness (`node C:/Users/Sohail/.venvs/auth-e-harness/audio-e.test.mjs`), no runner installed:

| Run | Result |
|---|---|
| **RED** — before `audioBlob.ts` existed | `FATAL cannot import … RED: the module under test does not exist yet.` exit 1 |
| **GREEN** | **`58 passed, 0 failed, 0 skipped`** — CG1-12 + CG-REQ1-4 (guard), RS1-6 (fail-fast transaction), CR1-4 (independent rollback), CS1-8 + CS-T1'-5' (identity/staleness), ST1-12 (clip store), FG1-2 + CG-D1-D5 (static shape of the component and the two pages) |

| Gate | Command | Result |
|---|---|---|
| Type-check | `npm run lint` (`tsc -b`) | **exit 0**. First attempt failed with one real error — `audioBlob.ts(193,48) TS18047: 'snap.attempt' is possibly 'null'` — fixed by narrowing through a local instead of a non-null assertion; no suppression used |
| Production build | `npm run build` | **exit 0**, `2603 modules transformed`, `dist/assets/index-*.js 1,152.10 kB (gzip 306.16)`. The >500 kB chunk warning is pre-existing and unrelated |

No test was weakened to reach these numbers. ST5 required `publishReady`/`publishError` to be rejected after `beginAttempt("")`, which Rev. 10's §5.1 snippet did not express; the store now refuses an empty-url publication — the test was not changed to fit the snippet.

### 11.5 Working-tree preservation (verified after all AUTH-E work)

`git status --porcelain` = **27 entries = the 20 pre-existing (15 ` M`, 5 `??`) + 7 AUTH-E paths**; `git stash list` = 0; branch and HEAD unchanged. The 7 are `audio_ownership.py`, `audioBlob.ts`, `ProtectedAudioPlayer.tsx` (untracked) and `hr.py`, `guesstimate.py`, `HRReport.tsx`, `GuesstimateReport.tsx` (modified). Those four were **clean** at baseline — their `git diff` contains only the AUTH-E hunks above, which also accounts for ` M` going 15 → 19 exactly. All 15 pre-existing modified files and all 5 pre-existing untracked paths are present and untouched.

AUTH-A artefact hashes: `tests/conftest.py` `01ae5b3a67d5…905bf` (matches the baseline), `test_authz_guard_static.py` `8b61c2fd042e…3aba`, `test_auth_fail_closed.py` `2a4b0d626e35…660c`, `app/routes/auth.py` `e597e203e429…e9b4`.

Bytecode: 4 `.pyc` were written today under `backend/**/__pycache__` (`auth`, `hr`, `guesstimate`, `audio_ownership`) — the `hr`/`guesstimate`/`audio_ownership` trio came from the 11:19 pre-GREEN run, before the `PYTHONDONTWRITEBYTECODE=1` convention was applied consistently; **0** have been written since 11:20. All are gitignored (`.gitignore:2 __pycache__/`), no `.pytest_cache` exists anywhere, and `frontend/tsconfig.tsbuildinfo` + `frontend/dist/` are gitignored build outputs of the sanctioned `npm run lint` / `npm run build`.

### 11.6 Disclosed deviations from the approved contract

1. **`stored_audio_path_matches` is *stricter* than the accepted "scheme ⇄ netloc pairing" clause.** A test of mine showed the pairing rule accepted `http://evil.example/api/hr/audio/<canonical>.webm` (both parts present), which would have let a stored absolute URL designate a foreign host as long as its path matched. It now rejects **any** non-empty scheme or netloc. Evidence that nothing visible regresses: the local SQLite datastore read read-only has **zero** rows whose `audio_url` contains `http` in either the HR question blob or the guesstimate column, and zero non-null guesstimate `audio_url` values. **Postgres / production is UNVERIFIED** — if a deployment stores absolute URLs, those clips now 404 until the write side (AUTH-C) stores root-relative paths. Weakening the check was not an option: the whole point of the guard is that the stored string is attacker-influenced data, not trusted input.
2. **`describeAudioError` is synchronous** (Rev. 4 described an async version that `await`ed the error Blob to recover FastAPI's `detail`). The backend's denial copy is a single uniform 404 string by design, so reading the body recovers nothing; the axios status branches are kept.
3. Rev. 10 §5.2's placeholder name `transportReason(err)` is shipped as the approved Rev. 4 name `describeAudioError(err)`. Same role, one fewer helper.
4. **Mandatory condition 2.1** implemented as: the install transaction's second step is `["publishReady", () => { if (!store.publishReady(gen, url)) throw new Error("ready-publication-rejected"); }]`, so `false` fails the transaction and drives the rollback branch; asserted by RS6/ST6 and statically by CG-D3.
5. **Mandatory condition 2.2 is NOT verified.** See §11.7.

### 11.7 Remaining risks and explicitly unverified behaviour

- **Browser lifecycle — all of FA / FA-R is unverified.** No server was started (separate approval required). Specifically, condition 2.2 ("`useSyncExternalStore` notification behaviour during actual unmount") is modelled at store level only: ST9 proves that after `unsubscribe` a write updates the snapshot and notifies nobody, so cleanup cannot schedule a React render through a listener. Whether React's own `forceStoreRerender` path is safe for a fiber being torn down is React's behaviour and was **not observed** (FA-R4). No DOM implementation is installed and installing one is out of scope, so a genuine unmount probe needs the browser pass. Mitigating code fact, verified statically by FG1: the component performs **no** `setState` in any cleanup — the only `useState` is the store itself and its setter is never destructured — so the classic "update on unmounted component" class cannot be triggered by our code.
- **`createClipStore` allocation count under StrictMode's double-invoked hook initializer** — a discarded store is inert (no listeners, no timers), but this is inference, not observation.
- **Residual TOCTOU (accepted Option A):** Starlette's `FileResponse` re-stats and opens the file at send time, so a file swapped between stage 4 and the send is not caught. Descriptor-pinned serving (`O_NOFOLLOW`) is AUTH-E2.
- **Write side still unenforced:** nothing yet proves that a `POST` can only write a recording into a session the caller owns (AUTH-C). AUTH-E closes the read door only.
- **`technical.py`'s `/audio/{filename}` route was not in AUTH-E's scope** and remained unauthorized when §11 was written. *(Closed 2026-11-03: `serve_technical_audio` at [technical.py:461](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/technical.py#L461) requires `get_current_user` and resolves the clip only through `resolve_technical_audio_path`, i.e. the same identity → ownership → stored-URL → confinement gates AUTH-E built for HR and Guesstimate, with the same uniform 404. The static guard that used to keep the boundary visible now pins the closed state at [test_authz_guard_static.py:192](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_authz_guard_static.py#L192), and the Technical report plays its clips through `ProtectedAudioPlayer` / `fetchProtectedAudio` like the other rounds. Everything above about browser lifecycle stays unverified for Technical too — its playback has had no browser pass.)*
- `docs/audits/AUDIT_SUMMARY.md` C-02 still lists the audio routes among the bypass set; the two AUTH-E routes are now closed there, the rest are not.

### 11.8 Next task

Per the agreed sequence **A → E → B → C → D → F**: **AUTH-B** (task #6) — the coach's hardcoded-identity contract. Before that, two AUTH-E follow-ups need a decision from the reviewer, not from me: (i) approve the **browser pass** (FA1-FA9, FA-A1/A2/B1, FA-C1-C3, FA-R1-R5, FA-Print) so §11.7's unverified items can be closed, and (ii) confirm whether the Postgres datastore holds any absolute stored `audio_url` that §11.6 item 1 would newly deny.

*(Superseded on 2026-11-01 — AUTH-B was contracted at Rev. 1, approved under decisions D1(b)/D2/D3/D4, implemented and verified. See §12. The two AUTH-E follow-ups above are still open.)*

## 12. AUTH-B — coach identity proven, not guessed (implemented 2026-11-01)

**Branch:** `feature/hr-round`  **HEAD:** `326d75e5e3c72f930ae39adb2ab3c4e634b0b392` — AUTH-B is **uncommitted**, as no commit was requested.
**Contract:** Rev. 1, approved with four decisions — D1(b) frontend error handling with the extra state distinctions, D2 `curriculum_agent.py` included, D3 NULL-owner plans inaccessible, D4 AUTH-B proceeds while AUTH-E stays open pending the browser pass. **Task:** #6.

### 12.1 Root cause

The coach router never established who was calling; it *guessed*, then treated the guess as an ownership credential. Four defects on one chain:

1. **Fail-open identity.** All four handlers used `_get_optional_user` (from `sessions.py`) and passed the result to a local `_resolve_user_id(current_user) → current_user.id if current_user else 1`. An anonymous, expired or malformed-token request was therefore served as **user 1** — the primary account on this host — with no 401 anywhere in the route.
2. **An explicit ownership bypass.** `complete_day` guarded with `if not plan or (plan.user_id and plan.user_id != user_id and user_id != 1)`. The trailing `and user_id != 1` meant the *guessed* principal could mutate **any** plan by `plan_id`, which the request body supplies and which is enumerable. This is the IDOR, and it was reachable without any credential.
3. **NULL-owner plans were publicly pooled.** Every read carried `| (CurriculumPlan.user_id.is_(None))`, and `auto_sync`'s guest branch read `(user_id == 1) | (user_id.is_(None))` for sessions — so an unauthenticated caller could see and advance plans belonging to no one, and the agent's `extract_candidate_history` did the same for sessions.
4. **The paid agent defaulted to the victim.** `generate_curriculum_plan(user_id: int = 1, …)` plus `state.get("user_id", 1)` inside `audit_history_node` meant a missing identity silently billed an OpenRouter run against account 1's telemetry.

### 12.2 Files changed by AUTH-B (exact scope — 5 paths, all approved)

| Path | Change |
|---|---|
| [backend/app/routes/coach.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/coach.py) | `_resolve_user_id` **deleted**; `_get_optional_user` import replaced by AUTH-A's `get_current_user`; all four handlers take `current_user: User = Depends(get_current_user)` and `user_id = current_user.id`; the three NULL-owner `or` clauses removed ([coach.py:47](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/coach.py#L47) :86 :240); `complete_day`'s guard is now `if plan is None or plan.user_id != user_id` ([coach.py:188](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/coach.py#L188)); `auto_sync`'s guest-pool branch replaced by a single `.where(SessionModel.user_id == user_id)` ([coach.py:261](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/coach.py#L261)) — 40 lines changed, no response shape touched |
| [backend/app/services/coach/curriculum_agent.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/services/coach/curriculum_agent.py) | guest-pool filter deleted from `extract_candidate_history` (now scopes to `user_id` only); `audit_history_node` reads `state["user_id"]` so an absent identity raises rather than defaulting ([curriculum_agent.py:243](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/services/coach/curriculum_agent.py#L243)); `generate_curriculum_plan`'s `user_id: int = 1` default **removed** — it is now a required positional |
| [backend/tests/coach_fixtures.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/coach_fixtures.py) | **new**, 360 lines — stub app with only `coach_module.router`, accounts with explicit PKs, plan/session builders, the autouse LLM stub, `read_plan()` (forces `expire_all`), `*.py` source-AST helpers. Never imports `main` |
| [backend/tests/test_coach_ownership.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_coach_ownership.py) | **new**, 568 lines / 42 test functions / **73 collected cases** |
| [frontend/src/components/Dashboard/CurriculumCoachCard.tsx](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Dashboard/CurriculumCoachCard.tsx) | +153 lines — failure taxonomy, `toCoachFailure`, `FailureBanner`, retry dispatch. **Not** the path named in the contract; see §12.6 |

Not touched, per §7: `auth.py` (including `_unauthenticated`/`get_current_user`), `sessions.py` (so `_get_optional_user` stays in place for its own consumers, and AUTH-A's static guard pinning it permissive still passes), `progress.py`, `analysis.py`, `feedback.py`, every AUTH-A and AUTH-E test/artefact, DB models, schema, migrations, dependencies, `speakvenv`.

### 12.3 API behaviour change

`GET /api/coach/active-plan`, `POST /api/coach/generate-plan`, `POST /api/coach/complete-day`, `POST /api/coach/auto-sync` now:

- **401 + `{"detail":"Could not validate credentials"}` + `WWW-Authenticate: Bearer`** for a missing header, an empty/malformed/foreign-signed token, an expired token, or a valid token whose subject was deleted — the AUTH-A uniform body, byte-identical across the four. Previously all four returned 200 as phantom user 1.
- **Ownership-scoped reads.** Only the caller's own `active` plan is visible; `user_id IS NULL` plans are invisible to everyone (D3), and generate-plan neither reuses nor archives one.
- **`complete_day`: uniform 404** (`"Curriculum plan not found"`) for missing, foreign *and* NULL-owner plans, with the session rolled back before the raise — a denial commits nothing. The old `user_id != 1` bypass is gone, so user 1 can no longer complete another candidate's day.
- **`auto_sync` and the agent's history query** filter on `SessionModel.user_id == user_id` only; orphans and other candidates' sessions never advance a curriculum.
- **200 responses are unchanged** in shape and content for an authenticated owner — asserted by the happy-path and response-shape tests, not assumed.
- Anonymous callers can no longer trigger `generate_curriculum_plan`, so a credential-less request can no longer bill an OpenRouter run.

### 12.4 Tests executed — actual results

Backend, from `backend/`, pytest staged outside the repo at `C:/Users/Sohail/.venvs/speakflow-testdeps` (speakvenv has none), `PYTHONDONTWRITEBYTECODE=1`, `--basetemp` inside `C:/Users/Sohail/.venvs/`:

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="C:/Users/Sohail/.venvs/speakflow-testdeps" \
  speakvenv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider \
  --basetemp="C:/Users/Sohail/.venvs/pytest-base-authB-final"
```

| Run | Result |
|---|---|
| **RED** — Phase A, tests only, before any fix | `51 failed, 22 passed` in `tests/test_coach_ownership.py`. The failures are the vulnerability, not plumbing: guest id 1 returned `success:true` while mutating a foreign plan; an *orphan* session (owner NULL) completed a curriculum day with `score_achieved 95.0`; a NULL-owner plan answered `active-plan` 200; and an anonymous `generate-plan` executed the stubbed agent. All 22 passes are shape/isolation assertions |
| **GREEN** — AUTH-B file alone | **`73 passed`** in 8.90s |
| **Full backend suite** | **`255 passed, 1 skipped`** in 23.45s |
| AUTH-A subset (`test_auth_fail_closed.py`, `test_authz_guard_static.py`) | **`41 passed`** — unchanged |
| AUTH-E subset (`test_audio_ownership.py`) | **`141 passed, 1 skipped`** — unchanged; the skip is AUTH-E's pre-existing Windows file-symlink case, not an AUTH-B one |

Coverage against the contract's 18 numbered items: (1) 4 routes × 4 bad-header forms — parametrized; (2) malformed Bearer; (3) expired; (4) valid token / deleted subject; (5) A cannot complete B's plan → 404; (6) B's plan byte-identical after the denial, via `read_plan()` + `expire_all` — including that the *next* day stays locked; (7) NULL-owner invisible to `active-plan`; (8) NULL-owner uncompletable by id; (9) `generate_plan` never writes NULL; (10) writes `current_user.id`; (11) generating for A neither reuses nor archives B's active plan (and refuses a NULL-owner one); (12) `auto_sync` sees only the caller's sessions — leak, foreign-session and NULL-owner-plan cases; (13) source + AST guards prove `user_id != 1`, `_resolve_user_id`, `current_user else 1`, `_get_optional_user`, `user_id.is_(None)` and `user_id > 1` are gone from `coach.py`, and `user_id > 1`, `user_id == 1`, `state.get("user_id", 1)` are gone from `curriculum_agent.py`; (14) all four handlers bind `get_current_user`, read from the parsed AST signature rather than a string grep; (15) happy-path 200 shapes (`{plan}` keys, day keys, `{success,…}`, `{synced:False,…}`, the 400 `"Day 42 not found in plan"`, last-day → `status == "completed"`); (16) the stub is *invoked* — `stub.calls` asserted, and `coach_module.generate_curriculum_plan is not stubbed_agent.real` proves the patch is on the attribute `coach.py` actually imported; (17) `test_the_run_uses_only_the_isolated_temp_envelope`; (18) AUTH-A's 41 and AUTH-E's 142 run green in the same invocation. Every denial test creates a **valid** row for the resource being denied, so a pass can never come from a missing fixture.

Beyond the 18 items (disclosed in §12.6): non-bearer scheme rejection, the agent's own `audit_history_node` raising `KeyError` without an identity, two cross-account session-telemetry tests, and a router-prefix guard.

Frontend — no test runner is installed in this project (the AUTH-E precedent is an out-of-repo Node harness; a vitest adoption is a separate decision, and the AUTH-B contract did not approve one). The client-side change is therefore gated by type-check and build, and *labelled* accordingly:

| Gate | Command | Result |
|---|---|---|
| Type-check | `npm run lint` (`tsc -b`) | **exit 0**, no suppression, no `any` escape hatch added |
| Production build | `npm run build` | **exit 0**, `dist/assets/index-CSQ0JseT.js 1,154.62 kB` (gzip 306.89 kB). The >500 kB chunk warning is pre-existing and unrelated |

*(The two backend counts above are the pre-hardening run. After the independent review's AB-04/AB-05 test hardening the AUTH-B file is **74 cases** and the full suite is **256 passed, 1 skipped** — see §12.10. §12.4 is kept as the record of the run that established AUTH-B GREEN the first time, with the 18-item coverage mapping it proved.)*

### 12.5 Working-tree preservation (verified after all AUTH-B work)

`git status --porcelain` = **30 entries** = the 27 baseline entries recorded in §11.5 **+ exactly the 3 tracked AUTH-B paths** (`backend/app/routes/coach.py`, `backend/app/services/coach/curriculum_agent.py`, `frontend/src/components/Dashboard/CurriculumCoachCard.tsx` — each **clean** at baseline, so their diffs contain only the hunks above; ` M` goes 19 → 22 and `??` stays 8). Zero removals; `git stash list` = 0; branch and HEAD unchanged. The one baseline entry whose *contents* changed is the untracked directory `backend/tests/`, which now also holds my two new AUTH-B test files — the pre-existing test files inside it were not edited.

AUTH-A artefact hashes re-verified after the last run: `tests/conftest.py` `01ae5b3a67d5`, `test_authz_guard_static.py` `8b61c2fd042e`, `test_auth_fail_closed.py` `2a4b0d626e35`, `app/routes/auth.py` `e597e203e429` — all identical to the §11.5 values. AUTH-E artefacts retain their 11:19–11:39 mtimes (`audio_ownership.py` 11:19, `ProtectedAudioPlayer.tsx` 11:38, `audioBlob.ts` 11:39), i.e. untouched by AUTH-B.

Bytecode: **0** `.pyc` written by the AUTH-B test runs (`PYTHONDONTWRITEBYTECODE=1`); the only new ones today are the 12:31 pair disclosed in §12.6 item 2, written by the reviewer's own live server, not by me. `frontend/dist/` and `tsconfig.tsbuildinfo` are gitignored outputs of the sanctioned `npm run lint` / `npm run build`. No `.pytest_cache` exists (`-p no:cacheprovider`, temp `--basetemp`).

### 12.6 Disclosed deviations from the approved contract

1. **The frontend path differs from the contract's.** §2 approved `frontend/src/components/Coach/CurriculumCoachCard.tsx` "verify the exact path before editing; do not assume it". No `components/Coach/` directory exists; the real consumer of `/api/coach/*` is [frontend/src/components/Dashboard/CurriculumCoachCard.tsx](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Dashboard/CurriculumCoachCard.tsx). I edited that file and created no new one. Same component the contract intended, correct path.
2. **The reviewer's live `uvicorn --reload` server hot-reloaded my edits.** I did not start, restart or signal any server (contract §6). While `coach.py` / `curriculum_agent.py` were on disk, the already-running reloader picked them up twice, at **12:31:02 and 12:31:21**, and each reload ran `main.py`'s startup hooks against **live PostgreSQL** — `base.metadata.create_all`, the ALTER-TABLE migration pass, `seed_hr_questions` ("HR question bank already populated (40 questions in database)" — idempotent, no rows written) — plus the audEERING warm-up, which made outbound `GET https://huggingface.co/api/models/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim` calls and logged an asyncio warm-up-callback ERROR at `main.py:101`. It also wrote 2 `.pyc` files (`coach.cpython-312.pyc`, `curriculum_agent.cpython-312.pyc`), both gitignored (`.gitignore:2 __pycache__/`) and left in place. The DDL pass is `CREATE TABLE IF NOT EXISTS`-style and the seed is existence-guarded, so no schema or data change is expected — but **[U]: I did not verify the live Postgres schema state after the reload**, because doing so is outside AUTH-B's read-only scope. Worth a `git stash`-free re-check on the reviewer's side if that server matters.
3. **Test coverage exceeds the 18 mandated items** — 42 functions / 73 cases. Extras: a `Basic …` header form, the 400 response shape, last-day completion, `extract_candidate_history` per-account isolation (2 cases), `audit_history_node` failing explicitly via `asyncio.run` + `pytest.raises(KeyError)`, and a router-prefix guard. No item was dropped.
4. **`Query` is imported but unused in `coach.py`.** Pre-existing, unrelated to the root cause, and §1 said "do not perform unrelated refactoring" — so I left it. A linter would flag it.
5. **No frontend unit tests** (see §12.4). The four error-state distinctions are implemented and type-checked, but the mapping 401 → sign-in, 403/404 → access, network/5xx → retry, 200-empty → existing empty state is asserted only by types and by reading the code — **[U]** in a browser.

### 12.7 Frontend error states as implemented (D1 amendment)

`toCoachFailure(err)` ([CurriculumCoachCard.tsx:39](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Dashboard/CurriculumCoachCard.tsx#L39)) classifies by `err.response?.status`, the project's existing axios convention, into `"auth" | "access" | "network"`; `FailureBanner` (:69) renders `role="alert"` with `text-error`, a Sign-in button only for `"auth"` (wired to `useAuth().openAuthModal`, the app's existing prompt — no auth logic duplicated, no token handling added here), and a Retry that calls `retryFailedRequest(request)` (:211) which dispatches the **original** action object (`load` / `generate{force}` / `complete{dayNumber}` / `sync`) back into the same handler, so retry re-issues the request rather than merely clearing the banner. Load failures live in `planFailure` and never `setPlan(null)`, so a failed request cannot render as a successful empty state; action failures live in `actionFailure` with the request that caused them, and the catch branches re-derive state from the server response instead of fabricating a plan.

### 12.8 Remaining risks and explicitly unverified behaviour

- **AUTH-B closes the coach only.** `progress.py`, `analysis.py`, `feedback.py`, `sessions.py`'s `_get_optional_user` consumers, the technical/HR/analysis **write** paths and the WebSocket handshake are untouched. **The dashboard is not now private**, and AUTH-C (#7), AUTH-D (#8), AUTH-F (#10) remain open. `docs/audits/AUDIT_SUMMARY.md` C-05 is closed for these four routes; DB-12 (the `user_id IS NULL` column with no NOT NULL constraint) is still live and AUTH-B deliberately changed no schema — new plans always carry an owner, but the column can still be NULL for any future writer.
- **SQLite-only dialect for these tests.** The isolated envelope is SQLite (`conftest.py`); the live datastore is PostgreSQL. The ownership predicates are dialect-neutral and the guest-pool deletion is a Python-side filter, so the risk is low, but the *exact* SQL against Postgres is **[U]**.
- **Rate limiting / abuse** on `generate-plan` (each accepted call can bill up to two OpenRouter completions) is out of scope and still unmitigated; AUTH-B only removes the anonymous path in.
- **The 401 for previously-working guest calls is a behaviour change** by design. Anyone using the coach UI without registering now sees the sign-in banner.
- **AUTH-E remains `in_progress`.** Task #9 and §11.7 stand unchanged: mandatory condition 2.2 and the whole browser-lifecycle set (FA / FA-R) are unverified pending the reviewer's approval of the browser pass, and the Postgres absolute-`audio_url` question is still open.

### 12.9 Next task

Per **A → E → B → C → D → F**, AUTH-B is done and the next security task is **AUTH-C** (task #7) — session/resource **ownership on the write side**, which also decides whether `_get_optional_user` stays permissive and what happens to the DB-12 NULL-owner column. It requires its own contract and its own approval; nothing of AUTH-C's was implemented here. Two AUTH-E follow-ups still need a reviewer decision (§11.8), and the AUTH-B browser/type-check gap in §12.6 item 5 closes only with a frontend test runner.

### 12.10 Post-review test hardening (AB-04, AB-05) — 2026-11-01

An independent read-only review of AUTH-B (reviewer: Antigravity; baseline branch `feature/hr-round`, HEAD `326d75e`, 30 working-tree entries verified before and after) returned **no AUTH-B-scoped vulnerability** but two test-strength findings, and a narrow follow-up task was approved for exactly one file: [backend/tests/test_coach_ownership.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_coach_ownership.py). No production code, no fixture, no AUTH-A/AUTH-E test, no dependency, no schema and no server was touched. Nothing was deleted or weakened; every change is an added assertion.

**AB-04 — denial tests must prove the request reached the guard.** Three tests previously compared only the database snapshot, so they would equally pass on an accidental 401, a 422, a router-level 404 or an early failure:

| Test | Assertions added before the snapshot comparison |
|---|---|
| `test_a_denied_complete_day_leaves_the_foreign_plan_untouched` (:126) | guest denial: `status_code == 404` **and** `json() == {"detail": PLAN_NOT_FOUND}`; anonymous denial: `status_code == 401` **and** `json() == {"detail": UNAUTHENTICATED}` |
| `test_a_denied_complete_day_does_not_unlock_the_next_day` (:154) | `status_code == 404` and the exact `PLAN_NOT_FOUND` body |
| `test_generate_plan_does_not_archive_a_foreign_active_plan` (:309) | the caller's own plan is now seeded as well, and the request is proven to have *completed* the replan: `status_code == 200`, `set(body) == {"has_plan","reused_existing","plan"}`, `reused_existing is False`, `body["plan"]["id"]` not either seeded plan id, **and** the caller's own row is `archived` while the victim's stays `active` — so the archive `UPDATE` is exercised and shown to be ownership-scoped, rather than inferred from a request that never got that far |

**AB-05 — the missing-plan leg of the uniform 404.** New `test_missing_foreign_and_unowned_plans_are_denied_identically` (:212): an authenticated caller issues `complete-day` against a foreign plan, a NULL-owner plan and an id that provably does not exist (`db.get(CurriculumPlan, absent_id) is None` asserted first, so "absent" is not assumed); each leg must answer `404` (:238) and the three responses are then compared as one `(body, content-type, WWW-Authenticate)` tuple, with the shared body equal to `{"detail": "Curriculum plan not found"}`. **What that comparison actually covers today:** the response **body** and **content type** are meaningfully compared across all three cases; `WWW-Authenticate` is collected into the same tuple, but `coach.py:189` raises its 404 without `headers=`, so the header is absent (`None`) in all three responses and that element provides no additional discrimination at present — it can only become meaningful if a future regression starts sending the header on one leg. Without the absent-id leg the suite could not notice a regression that answers 403, or a distinguishable "no such plan" body, for an unclaimed id — `plan_id` is enumerable, so that difference is a plan-existence oracle.

**Sensitivity proved at runtime, not argued** — out-of-repo read-only probe `C:/Users/Sohail/.venvs/auth-b-hardening/sensitivity_probe.py` (its own SQLite file under the scratch dir; the repository was not written to and the live PostgreSQL was not contacted). Against the real router, the accidental paths are distinguishable from the guard, so the exact-equality assertions cannot be satisfied by them:

| Request | Status | Body |
|---|---|---|
| ownership guard (foreign plan, valid token) | 404 | `{"detail": "Curriculum plan not found"}` |
| absent `plan_id`, valid token | 404 | `{"detail": "Curriculum plan not found"}` — byte-identical, which is the uniformity the new test asserts |
| no `Authorization` | 401 | `{"detail": "Could not validate credentials"}` |
| body missing `day_number` | 422 | `{"detail": [{"loc": ["body","day_number"], "msg": "Field required", …}]}` |
| unknown path | 404 | `{"detail": "Not Found"}` |
| wrong verb | 405 | `{"detail": "Method Not Allowed"}` |

The victim row was re-read after all six requests and was byte-identical to the pre-request snapshot.

**Results** (same commands and environment as §12.4, `PYTHONDONTWRITEBYTECODE=1`, pytest staged at `C:/Users/Sohail/.venvs/speakflow-testdeps`, temp `--basetemp`, `-p no:cacheprovider`):

| Run | Result |
|---|---|
| AUTH-B file alone | **`74 passed`** in 5.88s (43 test functions, up from 42 / 73) |
| **Full backend suite** | **`256 passed, 1 skipped`** in 15.98s |
| AUTH-A subset | **`41 passed`** — unchanged |
| AUTH-E subset | **`141 passed, 1 skipped`** — unchanged |

Frontend gates were not re-run: this task changed no `.ts`/`.tsx` file.

**Preservation.** `git status --short` = **30 entries** before and after; branch and HEAD unchanged. Must-not-touch hashes re-verified identical to the values captured at the start of this task: `tests/conftest.py` `01ae5b3a67d5`, `test_authz_guard_static.py` `8b61c2fd042e`, `test_auth_fail_closed.py` `2a4b0d626e35`, `tests/audio_fixtures.py` `4f6bf5a2ac5a`, `test_audio_ownership.py` `9a6f8ff27186`, `app/routes/coach.py` `9c491248f370`, `app/services/coach/curriculum_agent.py` `46198ebd25af`, `app/routes/sessions.py` `8599b3d4a8c1`. The only file whose hash moved is `tests/test_coach_ownership.py` (`c568cb535983…` → `a3dc80d71375…`; 568 → 631 lines). **0** new `.pyc` after 12:31; the two 12:31 ones remain the reviewer's live-reload artefacts recorded in §12.6, and the `cpython-314.pyc` trio under `app/**/__pycache__` predates this work (10-27 22:32) and is not a product of it.

**Deliberately not done.** The review also raised AB-09 (two vacuous conjuncts, [test_coach_ownership.py:81](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_coach_ownership.py#L81) and [test_coach_ownership.py:185](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_coach_ownership.py#L185)) and AB-10 (string-literal guards miss reworded fallbacks such as `user_id or 1`); neither was in the approved scope, so both remain open rather than being fixed opportunistically. AB-14's cosmetic note also stands: §12.2's line anchors for the NULL-clause removals read `:47 :86 :240` but the lines are 50 / 95 / 243 — the substance of §12.2 is otherwise accurate as re-verified by the reviewer.

**Still open from that review, unchanged by this task** — AUTH-B closed the curriculum-plan API only: **AB-01** (`/api/progress/*` and the sessions list still hand anonymous callers the user-1 + orphan pool — AUTH-C), **AB-02** (`/api/analysis/{session_id}/tts` and `/transcription` have no auth dependency at all, so the coach's spoken feedback for any enumerable session is still public — AUTH-D), **AB-03** (`create_plan` commits the archive before awaiting the agent, so a failure mid-generation leaves the candidate with no active plan), **AB-06/07/08** (frontend status-label copy, missing request-versioning, untracked 4 s timer), **AB-13** (SQLite-only dialect; the `created_at >= plan.created_at` comparison and explicit-PK fixtures need a PostgreSQL check). **AUTH-E remains `in_progress`** with its browser pass outstanding; **AUTH-B remains complete as recorded in §12 and §12.10**; the next task is AUTH-C, which needs its own contract and its own approval, and none of it was started here.

**Nothing in this checkpoint describes a planned task as completed.** Only AUTH-A, the two docs-only passes, the single orphan deletion, AUTH-E as recorded in §11 (with its browser items explicitly unverified), AUTH-B as recorded in §12, and the AB-04/AB-05 test hardening as recorded in §12.10 are done and verified by the commands reported there.

---

## 13. AUTH-C — session ownership: corrected endpoint inventory and approved decision record

**Status: CONTRACT ONLY — NOT IMPLEMENTED.** Recorded 2026-11-01. No production file, no test file, no dependency, no schema and no database was touched by this task; the only file written is this checkpoint. Task **#7 remains `pending`**. Two items in §13.9 require a reviewer decision before implementation starts.

### 13.1 Corrected endpoint inventory

Re-derived from the decorators actually present in the five approved files, cross-checked against the mounts in [backend/main.py:74-87](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/main.py#L74).

| Count | Value |
|---|---|
| Python handler functions in the five files | **35** (sessions 7 · progress 6 · hr 7 · guesstimate 7 · technical 8) |
| Handlers **in AUTH-C scope** | **22** |
| Handlers in those files **out of AUTH-C scope** | 13 (§13.1.3) |
| HTTP route operations for the 22 in-scope handlers | **29** (22 + the 7 `/api/jam` aliases of `sessions.router`) |
| Helper call sites (`load_owned_session`) | **13** |
| Handlers fixed by identity + owner-scoped query instead | 9 (sessions list + 2 creates, progress ×6) |

#### 13.1.1 Why the earlier figure said 16

`16` is not an endpoint inventory of AUTH-C's scope — it is the count of round-router handlers that bind `get_current_user`, a number that belongs to **AUTH-A** and is pinned by [backend/tests/test_authz_guard_static.py:15-20](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_authz_guard_static.py#L15) (`# Verified during the contract: 16 handlers authenticate through get_current_user.` with `EXPECTED_BOUND_HANDLERS = {"hr.py": 5, "guesstimate.py": 5, "technical.py": 6}`; 5+5+6 = 16). I re-derived those 16 from the decorators: `hr.py` :62 :116 :236 :264 :291 · `guesstimate.py` :63 :118 :206 :233 :262 · `technical.py` :62 :129 :145 :237 :382 :410. §1 line :19 of this document uses the same 16 in its AUTH-A sense. The AUTH-C audit text reused that number as though it described AUTH-C's surface, which is wrong on both axes: it **excludes** the 13 handlers that use the permissive `_get_optional_user` (7 in `sessions.py`, 6 in `progress.py` — the resolver that motivated AUTH-C at all), and it **includes** 7 round-router handlers that are not session-scoped (3 `/start`, 2 `/audio/{filename}`, 2 `/resume` writes). The correct scope is 22 handlers / 29 operations, and no endpoint was dropped to preserve the old number.

#### 13.1.2 The 22 in-scope endpoints

Every row below belongs in AUTH-C = **yes**. Paths are the real mounted paths; rows 1–7 are additionally reachable as `/api/jam/api/sessions…` aliases (§13.1.4).

| # | Method + path | Handler (file:line) | R/M | Auth today | Ownership today | Side effects that must follow the ownership check |
|---|---|---|---|---|---|---|
| 1 | `GET /api/sessions` | `list_sessions` [sessions.py:125](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L125) | read (collection) | optional (`_get_optional_user` :130) | **none** — anonymous callers get the guest pool `user_id == 1 OR user_id IS NULL` :138 | none (query only) |
| 2 | `POST /api/sessions` | `create_session` [sessions.py:145](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L145) | **write** (creates) | optional :154 | n/a — **creates NULL-owner rows** :172 | `_save_upload` writes video :159 and audio :161 to disk **before** `db.add`/`commit` :182-183 → identity must precede the file write (D-D) |
| 3 | `POST /api/sessions/json` | `create_session_json` [sessions.py:189](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L189) | **write** (creates) | optional :192 | n/a — **creates NULL-owner rows** :195 | none (no file write); client-supplied `overall_score`/`report` stay out of scope (H-09/H-10 excluded) |
| 4 | `GET /api/sessions/{id}` | `get_session` [sessions.py:222](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L222) | read | optional :226 | partial — `_get_session_for_user` :211-218 lets anonymous **and** NULL-owner through; foreign ⇒ **403** (existence oracle) | none; only builds the absolute `audio_url` :230 |
| 5 | `GET /api/sessions/{id}/audio` | `get_session_audio` [sessions.py:235](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L235) | read | optional :238 | partial, same helper :241 | `FileResponse` reads the candidate's recording — private-content disclosure, no mutation (**D-E** gate) |
| 6 | `PATCH /api/sessions/{id}` | `update_session` [sessions.py:256](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L256) | **write** | optional :260 | partial :262 | `setattr` loop + `db.commit` :264-265 — must follow ownership |
| 7 | `DELETE /api/sessions/{id}` | `delete_session` [sessions.py:276](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L276) | **write** | optional :279 | partial :281 | `db.delete` + `db.commit` :282-283 — **irreversible** (DB-10 file deletion remains out of scope) |
| 8 | `GET /api/progress/summary` | `get_summary` [progress.py:26](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/progress.py#L26) | read (aggregate) | optional :28 | **none** — `_user_session_filter` :18-22 guest branch, used :31 | none |
| 9 | `GET /api/progress/metrics` | `get_metrics` [progress.py:87](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/progress.py#L87) | read (aggregate) | optional :89 | none (filter at :94) | none |
| 10 | `GET /api/progress/technical` | `get_technical_progress` [progress.py:117](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/progress.py#L117) | read (aggregate) | optional :119 | none (:125) | none |
| 11 | `GET /api/progress/guesstimate` | `get_guesstimate_progress` [progress.py:249](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/progress.py#L249) | read (aggregate) | optional :251 | none (:257) | none |
| 12 | `GET /api/progress/hr` | `get_hr_progress` [progress.py:364](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/progress.py#L364) | read (aggregate) | optional :366 | none (:372) | none |
| 13 | `GET /api/progress/placement-readiness` | `get_placement_readiness` [progress.py:447](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/progress.py#L447) | read (aggregate) | optional :449 | none (`user_filter` :452) | none |
| 14 | `POST /api/hr/answer` | `submit_hr_answer` [hr.py:112](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/hr.py#L112) | **write** | **mandatory** (`get_current_user` :116) | **none** — `db.get(SessionModel, …)` :120 is owner-blind | audio written to disk :141-145 → `transcribe_audio` + `analyze_speech_emotion` :155-156 → `evaluate_hr_answer` (LLM) :170 → row mutation/commit. All must follow ownership. |
| 15 | `GET /api/hr/session/{id}` | `get_hr_session` [hr.py:234](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/hr.py#L234) | read | mandatory :236 | **none** — owner-blind :240 | none |
| 16 | `GET /api/hr/report/{id}` | `get_hr_report` [hr.py:262](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/hr.py#L262) | read | mandatory :264 | **none** — owner-blind :268 | none (verified read-only; 400 at :273 when no report) |
| 17 | `POST /api/guesstimate/submit` | `submit_guesstimate_answer` [guesstimate.py:113](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/guesstimate.py#L113) | **write** | mandatory :118 | **none** — owner-blind :122 | audio write :138-141 → transcribe/emotion :151-152 → `evaluate_guesstimate` :168 → commit |
| 18 | `GET /api/guesstimate/session/{id}` | `get_guesstimate_session` [guesstimate.py:204](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/guesstimate.py#L204) | read | mandatory :206 | **none** — owner-blind :210 | none |
| 19 | `GET /api/guesstimate/report/{id}` | `get_guesstimate_report` [guesstimate.py:231](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/guesstimate.py#L231) | read | mandatory :233 | **none** — owner-blind :237 | none |
| 20 | `POST /api/technical/answer` | `submit_technical_answer` [technical.py:233](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/technical.py#L233) | **write** | mandatory :237 | **none** — owner-blind :241 | audio write :264 → transcribe/emotion :278-279 → evaluation → commit |
| 21 | `GET /api/technical/session/{id}` | `get_technical_session` [technical.py:380](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/technical.py#L380) | read | mandatory :382 | **none** — owner-blind :386 | none |
| 22 | `GET /api/technical/report/{id}` | `get_technical_report` [technical.py:408](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/technical.py#L408) | read | mandatory :410 | **none** — owner-blind :414 | none |

`db.get(SessionModel, session_id)` appears at exactly 10 sites in these files — the 9 owner-blind round-router sites (#14–22) plus `sessions.py:213` inside `_get_session_for_user`, which serves #4–7. Those 13 handlers are the helper's call sites.

#### 13.1.3 Handlers in the same five files that are **not** in AUTH-C

| Handler | Why out |
|---|---|
| `GET /api/hr/tracks` [hr.py:43](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/hr.py#L43), `GET /api/hr/questions` :49, `GET /api/guesstimate/metadata` :46, `GET /api/guesstimate/random` :52 | Global catalog reads, no session access. `hr_questions` stays globally readable by design (**Q3**, DB-17). Adding an identity dependency here would also change the `EXPECTED_BOUND_HANDLERS` counts 5/5/6 that AUTH-A pinned — explicitly protected. |
| `POST /api/hr/start` :60, `POST /api/guesstimate/start` :61, `POST /api/technical/start` :143 | Already create the session **with** an owner (`hr.py:70`, `guesstimate.py:74`, `technical.py:162`) under mandatory auth. No defect to fix; covered by owner happy-path regression tests only. |
| `GET /api/hr/audio/{filename}` :289, `GET /api/guesstimate/audio/{filename}` :260 | AUTH-E, already owner-bound through `audio_ownership.py`, and pinned by `MEDIA_ELEMENT_ROUTES`. |
| `GET /api/technical/audio/{filename}` [technical.py:461](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/technical.py#L461) | C-04 / AUTH-E territory, so **explicitly excluded** from AUTH-C by Stage 4 — that exclusion is unchanged. Its state is not: it had no identity dependency when this table was written and was secured on 2026-11-03 as `serve_technical_audio`, binding `get_current_user` + `get_db` and delegating to `resolve_technical_audio_path`. What holds it is no longer a tripwire over an open hole but the wiring test at [test_authz_guard_static.py:192](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_authz_guard_static.py#L192), which fails if the identity dependency, the resolver call or the now-empty `UNAUTHENTICATED_MEDIA_ROUTES` inventory regresses. |
| `POST /api/technical/resume/upload` :60, `GET /api/technical/resume/status` :101, `DELETE /api/technical/resume` :128 | Operate on the caller's `ResumeProfile`, not on a `Session` row — user-scoped, not session-scoped. `/resume/status` legitimately uses `get_optional_current_user`. |

#### 13.1.4 Aliases and duplicate registrations

`sessions.router` is mounted **twice** — [main.py:75](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/main.py#L75) and [main.py:81](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/main.py#L81) `prefix="/api/jam"`, which yields the 11 `/api/jam` duplicate operations counted in `AUDIT_SUMMARY.md` §2 (7 from `sessions`, 4 from `analysis`). So rows 1–7 are 7 handlers / 14 operations. This is **two registrations of one handler, not a duplicate registration of the same path**: securing the handler secures both paths, so **no alias work is in AUTH-C's scope** and per **Q3** the aliases stay registered, unrenamed and unorganized. No frontend module requests `/api/jam/api/sessions…` and none requests `POST /api/sessions/json` (grep over `frontend/src` — zero hits), so the alias set is unreferenced legacy surface.

### 13.2 Approved decision record

| ID | Decision | Approved choice | Resulting contract |
|---|---|---|---|
| **D-A** | Shared helper location | **APPROVED** | New `backend/app/services/session_ownership.py`, created **during implementation, not now**. One public entry point that loads a `Session` and establishes ownership: requires an authenticated `User`; returns the row only when `session.user_id == current_user.id`; treats foreign, NULL-owner and nonexistent identically; raises the same 404 for all three; leaks no existence signal; importable from all five route modules without a circular import (it lives under `app/services/`, imports only `app.models.session` + `fastapi.HTTPException` + `User`, and **must not** import any route module — routes import the helper, never the reverse). |
| **D-B** | NULL-owner sessions | **Option 1 APPROVED** | Deny uniformly. No migration, no backfill, no automatic ownership assignment, no inference, and `sessions.user_id` **stays nullable** ([app/models/session.py:17](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/models/session.py#L17)). **Product-visible consequence (stated, not hidden):** legacy orphaned JAM sessions — including the `user_id IS NULL` pool today's dashboard and `/api/progress/*` surface for anonymous callers, and any pre-AUTH-A row — become inaccessible to every caller, including whoever recorded them. This is intentional and is the visible cost of closing the read; DB-12's missing NOT NULL constraint remains open by design. |
| **D-C** | Denial response | **Option 1 APPROVED** | Uniform `404` for foreign-owned, NULL-owner and nonexistent ids across all 13 helper call sites, **replacing the authenticated-foreign 403** at `sessions.py:217`. The detail string is identical across the three legs *of a given endpoint*. Recommendation for implementation (removes a copy-change risk while satisfying this rule): the helper raises `HTTPException(404, detail)` with the **caller's own existing "not found" string** — `"Session not found"` for rows 4–7 and the per-router strings for rows 14–22 (`"HR interview session not found."`, `"HR session not found."`, `"Guesstimate session not found."`, `"Technical interview session not found."`, `"Technical interview not found."`, `"Technical session not found."`); the round-type guard then runs **after** ownership and re-raises the same string, so `not session or session.round_type != X` collapses into two indistinguishable 404s and no existence oracle remains. **Implemented decision (recorded at acceptance, 2026-11-01):** the recommendation was not taken — `session_ownership.py:22` holds one shared `NOT_FOUND_DETAIL = "Session not found"` raised at every session-keyed site, JAM and round routers alike. This satisfies D-C's uniform-404 rule and goes one step further: per-router strings would have let a caller with several owned ids learn which id belongs to which round by probing the three endpoints, and the single detail removes that channel. Approved D-C governs; this note only records what shipped. Production behaviour was not changed by the audit. |
| **D-D** | Anonymous session creation | **APPROVED** | `POST /api/sessions` and `POST /api/sessions/json` take `Depends(get_current_user)` and always persist `user_id=current_user.id` (replacing the `… if current_user else None` at :172 and :195). No anonymous dev bypass, no settings flag. Consequence: the file write at :159/:161 now happens only after identity is proven, and **no new NULL-owner row can be created through these endpoints**. |
| **D-E** | JAM audio playback | **APPROVED — with two findings, §13.9** | `GET /api/sessions/{id}/audio` (#5) becomes ownership-gated, and the JAM consumer stops pointing an unauthenticated media element at the absolute URL that `session_media.py:65-70` emits. Reuse — not reimplement — the existing protected playback in [frontend/src/api/audioBlob.ts](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/audioBlob.ts) and [frontend/src/components/Recording/ProtectedAudioPlayer.tsx](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Recording/ProtectedAudioPlayer.tsx); change no other file; no player refactoring beyond this file. **AUTH-E's browser verification stays outstanding and is not closed by this change.** |
| **D-F** | Dashboard error handling | **APPROVED** | [frontend/src/pages/DashboardPage.tsx](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/pages/DashboardPage.tsx) stops presenting a failed progress request as a successful empty dashboard. Verified feasible: the page already uses react-query (`useProgressSummary` :23, `useProgressMetrics` :24) and checks **only** `isLoading` (:31), so `isError`/`error`/`refetch` are already on those objects — the four-way distinction (401 auth vs 403/404 access vs network/5xx vs 200-empty) and a Retry mapped to `refetch()` fit the existing architecture with no new abstraction and no redesign. Limited to progress-fetch error handling. |
| **D-G** | One coordinated implementation | **APPROVED, inventory corrected** | AUTH-C lands as a single change across the five backend modules plus the two narrow frontend files, using one helper so the security rule cannot be implemented inconsistently per router. The corrected counts are the ones in §13.1: **22 handlers / 29 operations** (not 16). |
| **Q1** | Static-guard amendment | **APPROVED (one conjunct)** | The only test edit is the `_get_optional_user` arm of [test_authz_guard_static.py:134-146](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_authz_guard_static.py#L134) — AUTH-C deletes that resolver, so its `return None` assertion cannot survive. The `get_optional_current_user` arm **stays** (still permissive, still used by `technical.py:102`). Everything else keeps its current meaning: `EXPECTED_BOUND_HANDLERS` 5/5/6, the AUTH-D analysis/feedback tripwire :167-170, the AUTH-E technical-audio tripwire :161-164, `MEDIA_ELEMENT_ROUTES` :155-158, and all AUTH-A/B/E tests. Also verified safe: [test_coach_ownership.py:529](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_coach_ownership.py#L529) and :538 reference `_get_optional_user` only in **negative** form ("not in bound"), so deleting the resolver cannot break AUTH-B. |
| **Q2** | Malformed `round_metadata` | **DEFERRED** | `except Exception: meta_dict = {}` at [sessions.py:168-169](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L168) is **not** changed to 400 in AUTH-C. Separate input-validation/error-handling issue; explicitly out. |
| **Q3** | Global HR questions + JAM aliases | **EXCLUDED** | `hr_questions` ownership model, query semantics and schema untouched (DB-17 design). `/api/jam` router aliases and registrations untouched — not removed, not renamed, not reorganized. |

### 13.3 Root cause (unchanged, restated for the corrected scope)

One defect, two shapes. **Shape 1 — by-id access (13 handlers):** the code proves a caller is *identified*, or doesn't even require that, and then loads a `Session` by client-supplied id without proving the row belongs to them. Concretely: `_get_optional_user` [sessions.py:67-83](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L67) returns `None` for no header (:73), for a malformed/unverifiable token (:80) and for a valid token with no matching row (:82); `_get_session_for_user` :211-218 then skips the ownership test entirely when `user is None`, skips it again when `session.user_id is None`, and answers an authenticated foreign caller with **403 while every other failure is 404** — an existence oracle on an enumerable integer PK; and the 9 round-router sites fetch the row with a bare `db.get(SessionModel, session_id)` that discards `current_user` (C-03). **Shape 2 — collection queries (9 handlers):** `_user_session_filter` [progress.py:18-22](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/progress.py#L18) and `list_sessions` :138 hand an anonymous caller the pooled rows `user_id == 1 OR user_id IS NULL` (AB-01), and the two create endpoints write `user_id=None` (C-02). Both shapes are the same missing predicate: `session.user_id == current_user.id` enforced before any read, write or side effect.

### 13.4 Current vs proposed behaviour

| Case | Today | After AUTH-C |
|---|---|---|
| no/invalid `Authorization` on any of the 22 | `sessions.py`/`progress.py`: succeeds as guest (list, aggregates, read, **PATCH/DELETE of pooled rows**, 201 + NULL-owner create); round routers: 401 from `get_current_user` | **401** `{"detail":"Could not validate credentials"}` with `WWW-Authenticate: Bearer` on all 22 (reuse `_unauthenticated()` / `_WWW_AUTHENTICATE`, [auth.py:112-120](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/auth.py#L112)) |
| authenticated caller, **own** session | 200/201/204, bodies as today | unchanged — same status codes, same response shapes (asserted, not just status) |
| authenticated caller, **someone else's** session | 200/204 with the other user's data (round routers, and `sessions.py` when `user_id IS NULL`); 403 only when both non-`None` | **404**, body identical to the nonexistent leg (§13.2 D-C); no row read, no commit, no file write, no transcription, no LLM call |
| **NULL-owner** session | readable, patchable, deletable by **anyone** (the `user_id is not None` guard skips the check) | **404** for every caller, owner-less included |
| **nonexistent** id | 404 `{"detail":"Session not found"}` / per-router string | same status, same string, byte-identical to the two rows above |
| anonymous `/api/progress/*`, `/api/sessions` list | pooled user-1 + orphan telemetry returned as if it were the caller's dashboard | **401** (no guest sandbox); after sign-in, only the caller's own rows |
| `GET /api/sessions/{id}/audio` | media element fetches an absolute URL with no credentials | ownership-gated; consumed through the authenticated blob-fetch path |
| `/api/jam/...` aliases | same handler, same hole | same handler, now secured — zero alias-specific edits |

### 13.5 API and frontend compatibility

- **No request body or response model changes.** `SessionOut`/`SessionDetailOut`/`SessionCreate`/`SessionUpdate` are untouched; `SessionUpdate` has no `user_id` field ([app/schemas/session.py:21-26](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/schemas/session.py#L21)), so PATCH can never be an ownership-transfer vector. The only response-body change is a denial leg's detail string, per D-C.
- All 22 are consumed through `apiClient`, which attaches the bearer token from `localStorage.speakflow_token` ([client.ts:12-22](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/client.ts#L12)); every route is already behind `ProtectedRoute` ([App.tsx:18-35,43-65](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/App.tsx#L18)), so a logged-in UI keeps working. **The behavioural cost is the guest path**: unauthenticated `/api/progress/*` and `POST /api/sessions` flip from 200/201 to 401, and pooled rows disappear from aggregates — the same class of change AUTH-B shipped for the coach (§12.3) and D-F now handles explicitly on the dashboard.
- Consumers that would otherwise mis-render the new failures: `DashboardPage.tsx:31` (fixed under D-F) and the `AnalysisResults.tsx` audio block (fixed under D-E). `client.ts:24-32` clears the token on 401 but does not redirect — recorded as existing behaviour, not widened here.
- `POST /api/sessions/json` has no in-repo caller; the 7 alias operations have no in-repo caller; the round routers are called only with their own prefixed paths.

### 13.6 Database impact

**None.** No model change, no DDL, no migration, no backfill, no index, no constraint, no `SELECT … FOR UPDATE` (C-07 excluded), no file-deletion lifecycle change (DB-10 excluded). `sessions.user_id` remains nullable and indexed as it is. The single deliberate data-visible consequence is D-B: NULL-owner rows become unreachable through these endpoints. All AUTH-C effects are request-path authorization decisions.

### 13.7 Exact permitted scope

Backend production: `sessions.py`, `progress.py`, `hr.py`, `guesstimate.py`, `technical.py`, and the new `app/services/session_ownership.py`.
Frontend: `components/Analysis/AnalysisResults.tsx`, `pages/DashboardPage.tsx` (both narrowly, per D-E/D-F).
Tests: new `backend/tests/test_session_ownership.py`, new `backend/tests/session_fixtures.py`, and **only** the Q1 amendment in `test_authz_guard_static.py`.
Excluded (do not touch): `coach.py`, `services/coach/curriculum_agent.py`, `analysis.py`, `feedback.py`, `emotion_stream.py`, `services/audio_ownership.py`, `technical.py:436 stream_technical_audio`, all models/schema, all migrations, dependency files, AUTH-A/B/E tests beyond Q1, C-07, DB-10, H-09/H-10, and the Q2 metadata handler.

### 13.8 Test-first plan, retargeted to the corrected inventory

Written RED first against the isolated envelope in [conftest.py:19-22](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/conftest.py#L19) (temp SQLite under `tempfile.mkdtemp`, `atexit` cleanup; **`main.py` must never be imported** in a way that runs its `startup` hook — reuse the `probe_app`-style pattern and monkeypatch at the attribute each route module imported, exactly as the coach/audio fixtures do).

| Class | Coverage |
|---|---|
| Authentication | each of the 22 without a header ⇒ 401 + exact body + `WWW-Authenticate`; invalid/expired/unknown-`sub` token ⇒ same |
| Ownership denial | each of the 13 helper sites: foreign session ⇒ **404 + exact detail asserted before any DB comparison** |
| NULL-owner | same endpoint, `user_id IS NULL` ⇒ byte-identical 404 to the other two legs |
| Nonexistent | id **provably absent first** (`db.get(SessionModel, absent_id) is None`, `absent_id` beyond every seeded id) ⇒ same 404 |
| No existence oracle | foreign / NULL-owner / nonexistent compared as one `(status, body, content-type)` tuple per endpoint |
| Cross-user mutation | PATCH/DELETE on `sessions.py` and `/answer`+`/submit` against a foreign id ⇒ persisted row byte-identical to the pre-request snapshot (all columns incl. `round_metadata`, `report`, `duration_seconds`, plus child rows) |
| Side-effect prevention | denied `/answer`+`/submit`: transcription and evaluation/LLM stubs **not invoked** (assert call-count 0 on the patched `transcribe_audio` / `analyze_speech_emotion` / `evaluate_hr_answer` / `evaluate_guesstimate` attributes) **and no file created on disk** under the temp upload root; denied PATCH/DELETE: no commit occurred; denied `create_session`: no upload written |
| Owner happy path | every in-scope endpoint with a genuine owner ⇒ today's status **and** today's response shape (key sets, types, `audio_url` presence), so no silent contract drift |
| Progress response shape | all 6 aggregates for an owner with rows, an owner with none, and a mixed pool — shape stays as `AUDIT_SUMMARY` documented, and another user's sessions cannot move the numbers |
| Static / AST guards | helper bound in all 13 by-id handlers; `get_current_user` bound in all 22; `_get_optional_user` and the guest predicate `(SessionModel.user_id == 1) | SessionModel.user_id.is_(None)` gone from `progress.py`; the **Q1-amended** `test_authz_guard_static.py` keeps 5/5/6 and both tripwires; no route module imported by `session_ownership.py` (circular-import guard) |
| Cross-module regression | AUTH-A 41, AUTH-B 74, AUTH-E 141+1 stay green unmodified (beyond Q1); each `/api/jam` alias asserted once per sessions handler to prove it inherits the fix. **As built (verified at acceptance):** one behavioural alias test — `jam.get` — not seven;** the other six alias operations are secured because they share the same handler objects and every sessions handler's `get_current_user` binding is covered by the static guard |

Coverage rule: every one of the 22 handlers is exercised by at least the authentication, denial and owner-happy-path classes; the 7 alias operations inherit from their handler and are covered by parametrized path pair rather than duplicated.

**Not run in this task.** No test was executed, created or modified while writing §13.

### 13.9 Risks, dependencies, and two items needing a reviewer decision

1. **STOP-AND-REPORT (D-E paths).** The approved text names `frontend/src/utils/audioBlob.ts` and `frontend/src/components/ProtectedAudioPlayer.tsx`. **Neither path exists.** The real AUTH-E artefacts are `frontend/src/api/audioBlob.ts` and `frontend/src/components/Recording/ProtectedAudioPlayer.tsx` (verified by glob; both are read-only imports, so no scope expansion is implied — neither is in Stage 4's writable list and neither needs editing). Recommend the contract adopt the real paths.
2. **STOP-AND-REPORT (D-E drop-in incompatibility).** `ProtectedAudioPlayer` takes `{audioUrl?, className?}` and renders a native `<audio controls>` hidden until ready plus "Loading…"/"Playback unavailable: {reason}" ([ProtectedAudioPlayer.tsx:29,152-172](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/components/Recording/ProtectedAudioPlayer.tsx#L152)). It exposes **no** ref, `currentTime`, `duration`, seek or play/pause. `AnalysisResults.tsx` has a bespoke player: play/pause button (:506-520), seek slider (:523-533), current/duration readout with `--:--` (:534-543), a "Ready / Loading recording… / Preparing playback" chip (:410-414), per-`MediaError.code` copy (:53-67) and a Retry button (:487-501). Swapping in the component would **delete working UI**, which "preserve existing playback behaviour" forbids; keeping the UI while only fetching through the component is impossible because the component owns the element. **Recommended resolution (needs approval):** reuse the *primitives* — `toApiPath` / `fetchProtectedAudio` / `describeAudioError` and the object-URL lifecycle `playbackReleaseSteps` + `attemptCleanup` + `runSequential` — inside `AnalysisResults.tsx`, letting that file keep its custom controls while the element's `src` is written only from a `blob:` URL it mints and revokes itself. `toApiPath` already re-homes the absolute `/api/sessions/{id}/audio` URL onto its pathname when the origin is configured ([audioBlob.ts:63-87](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/api/audioBlob.ts#L63)), so the server-side absolute URL is not a blocker; `ProtectedAudioPlayer` itself stays unmodified. If the reviewer instead wants the component, that is an approved UI reduction and must be stated as such.
3. **D-B orphans.** Any real orphaned JAM recording a user still wants becomes unreachable by design. No backfill is permitted, so preserving those rows belongs to a separate, explicitly approved data task.
4. **Denial-body variance.** Rows 14–22 today answer per-router strings and, for a foreign session, answer **200 with the victim's data**; a client that branches on 403 would need re-checking, but grep shows no frontend consumer inspects a 403 on any of these paths.
5. **Sequencing.** AUTH-C lands after AUTH-A (done) with AUTH-E's browser pass still open (#9, #19). It closes **AB-01**; it does **not** close AB-02 (AUTH-D), C-04 (AUTH-E), C-07, DB-10, H-09/H-10, DB-12 or Q2. AUTH-F (#10) remains untouched — the `/ws/session/{id}/emotion` handshake still carries no authorization, so AUTH-C does not make the live path private.
6. **Dialect.** SQLite-only evidence, as throughout this checkpoint; PostgreSQL behaviour remains `[U]`.

### 13.10 Next task

Await explicit approval of §13 — including the two §13.9 decisions — before any implementation. On approval the order is: `session_ownership.py` helper → tests RED → rewire the 13 by-id sites → identity + owner-scoped queries for the remaining 9 → Q1 static-guard amendment → D-E frontend → D-F dashboard → full-suite verification → §14 records the actual test results. Nothing in this section describes work that has been done.

## 14. AUTH-C — session ownership enforced (implemented 2026-11-01)

Status: **complete for the approved scope.** AUTH-E remains `in_progress` (its browser pass is still outstanding, #19); AUTH-D (#8) and AUTH-F (#10) have not been started.

### 14.1 Root cause, as closed

The 22 session-keyed handlers took their identity from `_get_optional_user` (or from no dependency at all in `progress.py`), and the by-id resolver checked only that a row existed, so an anonymous caller was served the user-1 + `user_id IS NULL` guest pool and an authenticated caller could read, patch, delete, transcribe, evaluate and stream **any** session by id. Ownership is now established in the backend, in one helper, before any effect.

### 14.2 Files changed by AUTH-C (exact scope — 10 paths, all approved)

| Path | Purpose of the change |
| --- | --- |
| `backend/app/services/session_ownership.py` | **new.** The single ownership rule: `owned_session`, `owned_round_session` (round-type guard runs *after* ownership and re-raises the same 404), and `owned_session_scope` for collection queries. Imports only `models` and `fastapi`/`sqlalchemy` — never a route module. |
| `backend/app/routes/sessions.py` | 7 handlers now bind `get_current_user`; `_get_optional_user` and the 403/NULL-permissive `_get_session_for_user` deleted; both create handlers persist `current_user.id`; `list_sessions` uses the owner scope; read/patch/delete/audio call `owned_session` before any effect. |
| `backend/app/routes/progress.py` | 6 handlers now bind `get_current_user`; `_user_session_filter` (the `user_id == 1 OR user_id IS NULL` branch) deleted; every aggregate query filtered by `owned_session_scope`. No longer imports the sessions router. |
| `backend/app/routes/hr.py` | `answer_hr_question`, `get_hr_session`, `get_hr_report` fetch through `owned_round_session(..., round_type="hr")`. Post-ownership checks (`detail missing`, `already completed`) kept as-is. |
| `backend/app/routes/guesstimate.py` | Same for `submit_guesstimate_answer`, `get_guesstimate_session`, `get_guesstimate_report` (`round_type="guesstimate"`). |
| `backend/app/routes/technical.py` | Same for `submit_technical_answer`, `get_technical_session`, `get_technical_report` (`round_type="technical"`). |
| `backend/tests/session_fixtures.py` | **new.** Mounts only the five session-keyed routers, registers the 22/13/9 inventory, stubs every processor at the attribute the *route module imported*, and provides the upload-snapshot, commit-counter/commit-fault and AST guards. |
| `backend/tests/test_session_ownership.py` | **new.** 13 test categories, 287 cases. Every denial asserts status → full body → persisted state, in that order, and every by-id denial first requires an owner control to succeed so a 422/405/wrong-route 404 cannot masquerade as a denial. |
| `backend/tests/test_authz_guard_static.py` | The single Q1 amendment: the guard that required the now-removed `_get_optional_user` to still exist is dropped; `get_optional_current_user` coverage in `auth.py` is preserved and the test renamed to match. |
| `frontend/src/components/Analysis/AnalysisResults.tsx` | D-E. The existing custom player is kept and its source is now an authenticated blob (details in 14.6). |
| `frontend/src/pages/DashboardPage.tsx` | D-F. Failed progress/session requests are reported as failures, not as an empty dashboard (14.7). |

Not modified, by instruction: `ProtectedAudioPlayer.tsx`, `audio_ownership.py`, `audioBlob.ts`, `coach.py`, `curriculum_agent.py`, `analysis.py`, `feedback.py`, `emotion_stream.py`, every model/migration/requirements file, and the `/api/jam` alias registrations.

### 14.3 API behaviour change

| Case | Before AUTH-C | After AUTH-C |
| --- | --- | --- |
| no/invalid `Authorization` on any of the 22 | `sessions.py`/`progress.py` served the guest pool (200/201, incl. PATCH/DELETE of pooled rows) | `401 {"detail":"Could not validate credentials"}` + `WWW-Authenticate: Bearer` on all 22 |
| foreign session id | read: victim's data (200); `sessions.py` by-id: `403 Access denied` | `404 {"detail":"Session not found"}` for the JAM routes; per-router "not found" strings for the round routes |
| `user_id IS NULL` orphan | reachable by any caller | same 404 as a foreign row |
| foreign vs orphan vs absent | distinguishable (403 / 200 / 404) | indistinguishable — verified byte-identical, and the `WWW-Authenticate` header is `None` on all three legs, so it carries no discriminating signal either |
| denied write/analysis request | Whisper, emotion, evaluator, LangGraph and Mem0 all ran; the clip was written to disk; a commit was issued | zero processor calls, zero new files, zero commits (each measured against a stub/fixture that the *owner* request proves is live) |

The guest path is the behavioural cost: unauthenticated `/api/progress/*` and `POST /api/sessions` now answer 401, and pooled rows leave the aggregates.

### 14.4 Tests executed — actual results

| Step | Command (from `backend/`, `speakvenv`, `PYTHONPATH=…/speakflow-testdeps`, `--basetemp` outside the repo) | Result |
| --- | --- | --- |
| RED — fixtures registered, before any implementation | `pytest tests/test_session_ownership.py -q` | **182 failed, 105 passed** in 28.44 s |
| GREEN — focused AUTH-C suite | same | **287 passed** |
| Full backend suite | `pytest tests -q` | **543 passed, 1 skipped** |
| AUTH-A subsets | `test_auth_fail_closed.py`, `test_authz_guard_static.py` | 26 passed; **15 passed** (was 41 total before the rename; count unchanged, one test amended in place) |
| AUTH-B subset | `test_coach_ownership.py` | **74 passed** — exactly the recorded baseline; its `_get_optional_user` references are negative assertions and still hold |
| AUTH-E subset | `test_audio_ownership.py` | **141 passed, 1 skipped** — exactly the recorded baseline |
| Frontend gates | `npm run lint` (= `tsc -b`), `npm run build` | exit **0** and **0**; `tsc -b` clean, `vite build` 2603 modules, 1 157.34 kB JS chunk (pre-existing size warning, not an error) |

Arithmetic reconciles with the §12/§13 baselines: 26 + 15 + 74 + 141 = 256, the exact pre-AUTH-C total, and 256 + 287 = 543. Corrected at acceptance: the sums above omit AUTH-E's one skip; with it the exact reconciliation is 26 + 15 + 74 + 141 + 1 = 257 and 287 + 257 = 544 = the 543 passed + 1 skipped. No pre-existing test was deleted, renamed away, or skipped to reach GREEN.

**RED classification.** The failures were the vulnerability, not plumbing. The categories exercised (case counts are the sizes of those tests in the current file, not a partition of the 182): 52 of the 88 bad-credential cases — exactly the 13 anonymously-capable handlers × 4 header forms; all 13 foreign, 13 NULL-owner, 13 no-longer-403, 13 uniform-oracle, 13 no-commit and 13 forced-commit-fault denials; 3 no-processing and 3 no-disk-write refusals; 7 guest-pool aggregates; 22 of the 22 "helper is used" guards; plus the pool/resolver/metadata/alias/deleted-subject static singletons. Sampled evidence captured during RED: anonymous `GET /api/progress/summary` returned `{"total_sessions":2,…}`; `POST /api/hr/answer` on a foreign session returned **200** with `"audio_url":"/api/hr/audio/session_1_hr_q_2_3.webm"`. The category list is a description of what failed; the 182 total is the run's own output.


### 14.5 Test-side corrections made during this task (disclosed, none weakens an assertion)

1. `assert stubbed_processing.count == 0` compared a **bound method** to `0`, so the assertion could never hold. Corrected to `.count()` at [test_session_ownership.py:206](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_session_ownership.py#L206) and :283. During RED those 16 cases contributed no signal; they are real assertions from here on. (`CommitCounter.count` is a genuine `@property` and was left alone.) **Acceptance-audit correction:** the two preserved RED captures (`C:/Users/Sohail/.venvs/authc-red.txt`, `authc-red2.txt`) contain no bare `count == 0` — `.count()` was already in place at both recorded RED runs — and the 16 is the collected-case size of these two assertion sites (13 + 3), not 16 separate bare comparisons in the file. The two denials failed earlier, at `assert_exact_denial`, so the side-effect lines were unreachable in RED — no false evidence was produced either way. (Cited lines shifted when the snapshot reordering landed: the assertions are at :211 and :288 — the same §12.10 AB-14 anchor-drift class.)
2. The by-id denial test ran its owner control *before* snapshotting the call log and upload directory, so for the three answer endpoints the caller's own legitimate transcription/emotion/graph calls and clip write were being attributed to the refusal. The snapshots now happen after the control, which is what the assertion was always meant to measure. **Acceptance-audit chronology correction:** the ordering fix landed during GREEN — preserved RED2 still prints the old arrangement (`files_before = upload_snapshot()` before the owner control) — so the recorded RED2 (`182 failed, 105 passed`) remains valid evidence from the vulnerable tree, but the *final* arrangement was never separately demonstrated failing against that tree.
3. `hr.py`'s helper import was inserted mid-statement by an earlier edit and broke the module; detected by the compile check and repaired. (The commit-fault fixture that came out of this work leaves one assertion weak: `assert fault is not None` in the commit-fault test can never fail, because `arm()` returns `self`.)
4. Two fixture-level fixes carried in from the RED phase: pytest only registers fixtures imported into the test module, and round clip filenames are deterministic (`session_{id}_…_{uid}.webm`) with ids repeating across tests, so exact-path assertions replaced name-set diffs.

*Acceptance-audit record: the commit-fault pair has one more limit. The owner-fault test proves a forced commit failure surfaces instead of being swallowed into a success, but neither test asserts the persisted row's state after the failure — so rollback correctness is not established by this suite. Neither test was changed, and no rollback verification is claimed.*

### 14.6 D-E — JAM playback, as implemented

Only `AnalysisResults.tsx` changed. The bespoke player (play/pause, seek slider, current/duration, ready/loading strip, MediaError-specific copy, Retry, teardown) is retained; `ProtectedAudioPlayer` was **not** substituted for it. `src={audioUrl}` is gone from the `<audio>` element — React never writes that attribute now — and the clip is fetched through `fetchProtectedAudio(apiClient, …)` with an `AbortController`, installed via `URL.createObjectURL` + `setAttribute`/`load` inside `runSequential`, and released through `playbackReleaseSteps`/`attemptCleanup` (failures are `console.error`-reported, never swallowed). `isStaleResponse(attempt, clipAttempt.current, aborted)` gates both install and error publication, so a superseded or unmounted settle cannot replace a newer recording or touch state; cleanup bumps the generation before releasing, which is what makes "no update after unmount" hold. Retry re-dispatches the authenticated fetch (`setRetryToken`) instead of calling `audio.load()` on a source React no longer owns. `describeAudioError` supplies the 401/403/404 copy; decode errors keep their existing MediaError strings verbatim.

### 14.7 D-F — dashboard failure states, as implemented

Only `DashboardPage.tsx` changed. Each of the seven AUTH-C-scoped queries is inspected with React Query's own `isError`/`error`/`refetch`; failing sections are named in a `role="alert"` panel with copy that separates **401** (expired session), **403/404** (not available for this account), **other HTTP status**, and **no response at all** (network/5xx), plus a Retry that refetches only the failed queries. The affected dashboards are not rendered when their request failed, so a failed progress request can no longer present as "no practice yet" — and a legitimate empty result still renders exactly as before. No new abstraction, hook, store or layout was introduced.

### 14.8 Working-tree preservation (verified after all AUTH-C work)

Branch `feature/hr-round`, HEAD `326d75e5e3c72f930ae39adb2ab3c4e634b0b392`, `git stash list` = 0, never staged or committed. `git status --porcelain` moved from the expected 30 entries (22 ` M` + 8 `??`) to **26 ` M` + 9 `??` = 35**, and the five added entries are exactly the five paths this task created or newly modified: `backend/app/routes/sessions.py`, `backend/app/routes/progress.py`, `backend/app/routes/technical.py` and `frontend/src/pages/DashboardPage.tsx` were **clean at HEAD** (HEAD's `sessions.py` still contains `_get_optional_user` 8×) and became modified, and `backend/app/services/session_ownership.py` is the one new untracked path. The other 30 baseline entries are all still present; `hr.py`, `guesstimate.py` and `AnalysisResults.tsx` were already ` M` and remain so. `backend/tests/` stays a single untracked entry whose *contents* grew — the pre-existing test files inside it were not edited, except for the approved Q1 amendment to `test_authz_guard_static.py`. No reset, clean, stash, checkout, branch switch, server start, migration, dependency install or live-database contact was performed.

**Acceptance-audit verification (2026-11-01): the composition above re-verified and stands — 26 ` M` + 9 `??` = 35** (the audit's interim "23 + 12" figure was its own parse error and is superseded; the 35 total was always right). One claim in this paragraph was wrong and is corrected here: **`DashboardPage.tsx` was *not* clean at HEAD.** It was one of the pre-existing ` M` entries at the §11.5 baseline (it already differed from HEAD before AUTH-C began), and AUTH-C added only its D-F hunks to an already-modified file. The precise, verified statement: of the ten AUTH-C paths, `sessions.py`, `progress.py` and `technical.py` had no working-tree change of their own before this task (their diffs vs HEAD contain only the AUTH-A/AUTH-E hunks recorded in §3/§5 and §11.2/§11.5 plus the AUTH-C hunks — no unrelated content); `hr.py`, `guesstimate.py`, `AnalysisResults.tsx` and `DashboardPage.tsx` were **already modified at the baseline** and gained AUTH-C hunks; `session_ownership.py`, `session_fixtures.py` and `test_session_ownership.py` are new files inside already-untracked paths. Of the 26 ` M` entries today, **21 are pre-existing modifications from earlier tasks and feature work that AUTH-C did not touch** (`analysis.py`, `auth.py`, `coach.py`, `emotion_stream.py`, `main.py`, `requirements.txt`, the four service files, `curriculum_agent.py`, `RecordingSession.tsx`, `useLiveEmotionStream.ts`, `LiveConfidenceNeedle.tsx`, `VocalDeliveryCard.tsx`, `CurriculumCoachCard.tsx`, both Report pages, `types/index.ts`) — the 35-entry total must never be read as 35 AUTH-C changes.

### 14.9 Frontend verification limits

`tsc -b` and `vite build` prove the code type-checks and bundles. **No browser run was performed and none is claimed** — object-URL playback, abort/teardown behaviour under a real media element, and the dashboard's four failure states are `[I]` until someone drives them in a browser. That gap is the same one AUTH-E has been carrying, and AUTH-E's browser pass (#19) is still open.

### 14.10 Deferred and out-of-scope findings (unchanged by this task)

- **Malformed `round_metadata`** at [sessions.py:149-150](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/sessions.py#L149) — the `except Exception: meta_dict = {}` that turns an unparseable metadata payload into a silent empty dict (the contract cited it as :168-169; my rewiring of the handlers above it moved the lines, the code is byte-identical and still unfixed). Explicitly deferred by §4; **unchanged by AUTH-C**.
- **C-04 / AUTH-E**: `GET /api/technical/audio/{filename}` still resolves by filename without ownership, and the guard test pins that it binds no identity dependency, so a future edit cannot silently half-fix it. *(Corrected 2026-11-03 — this was the state at the AUTH-C baseline, not the current one: the handler is now `serve_technical_audio` at [technical.py:461](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/technical.py#L461), authenticated, ownership-checked against the session's own stored question URLs, confined to `technical_audio/`, and denied with the same uniform 404 as every other audio miss. The pin still exists but points the other way: [test_authz_guard_static.py:192](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/tests/test_authz_guard_static.py#L192) fails if the identity dependency, the resolver call or the empty unauthenticated-media inventory regresses, so a future edit still cannot silently half-fix it.)* AUTH-E's browser pass remains outstanding.
- **AUTH-D (#8)**: `/api/analysis/{id}/tts` and `/transcription` still have no auth dependency (AB-02 open). *(Closed 2026-11-01 by the work recorded in §15 — this line is kept as it was written at the AUTH-C baseline.)*
- **AUTH-F (#10)**: the `/ws/session/{id}/emotion` handshake carries no authorization. **AUTH-C does not make the live path private.**
- **C-07** (`SELECT … FOR UPDATE`), **DB-10**, **DB-12**, **H-09/H-10**, **Q2/Q3** untouched.
- **Schema**: `sessions.user_id` is still nullable and no legacy NULL-owner row was migrated or backfilled, so those rows are unreachable by design (D-B). A backfill needs its own approved data task.
- **Dialect**: all evidence is SQLite; PostgreSQL behaviour remains `[U]`, including the owner-scoped aggregates in 14.3.

**AUTH-C does not mean every session is private.** It closes AB-01 for the 22 session-keyed handlers; AUTH-D, AUTH-E and AUTH-F are separate security workstreams that still have open paths.

---

## 15. AUTH-D — analysis + feedback authorization enforced (implemented 2026-11-01)

Approved task: decisions D-A1…D-A10, five handlers — `POST /api/sessions/{id}/analyze`, `GET .../analysis`, `GET .../transcription`, `GET .../tts` in [analysis.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/analysis.py) and `GET .../feedback` in [feedback.py](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/feedback.py) — plus the D-A5 frontend correction. No schema change, no migration, no service rewrite.

### 15.1 Root cause, as closed

These five handlers keyed on the *row*, not the *caller*. Four resolved the session with `db.get(SessionModel, session_id)` and treated "the id exists" as authorization; `get_feedback` never read the session at all and selected `AIFeedback` by `session_id` directly, so the parent's owner was never consulted. `/analyze` went further: it wrote `session.status = "processing"` and committed **before** any identity existed in the request, so an anonymous caller could drive another user's session into Whisper, MediaPipe, audEERING/Praat and Ollama and overwrite its transcript, metrics, feedback and report.

### 15.2 Files changed by AUTH-D (exact scope — 8 paths, all approved)

| Path | Change |
| --- | --- |
| `backend/app/routes/analysis.py` | +`get_current_user`, `User`, `owned_session` imports; all four handlers gated; now-unused `Session as SessionModel` import dropped |
| `backend/app/routes/feedback.py` | same three imports; `get_feedback` gated, query re-keyed to `session.id` |
| `backend/tests/session_fixtures.py` | additive only: `AUTHD_ENDPOINTS` registry, analysis/feedback processor stubs, TTS cache helpers, `make_analysis_target`, `read_children`, `analysis_app`, `analysis_alias_app` |
| `backend/tests/test_analysis_authz.py` | new — 36 functions / 106 cases across 10 categories |
| `backend/tests/test_authz_guard_static.py` | the AUTH-D tripwire retargeted into two guards (15 → 18 cases) |
| `backend/tests/test_session_ownership.py` | exclusion list narrowed from 4 modules to 2 (287 → 285 cases); nothing else touched |
| `frontend/src/pages/AnalysisPage.tsx` | D-A5 failure states |
| `docs/audits/IMPLEMENTATION_CHECKPOINT.md` | this section, plus the annotation on §14.10's now-closed AUTH-D bullet |

`main.py`, `session_ownership.py`, `services/tts.py`, the feedback-generation service, the emotion/prosody/transcription/tracking services and the technical audio routes were not modified.

### 15.3 API behaviour change

| Handler | Before | After |
| --- | --- | --- |
| `analyze_session` | anonymous; `db.get` + `404 "Session not found"`; status write and commit preceded any identity | gate at [analysis.py:98](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/analysis.py#L98) — `owned_session`, outside the broad `try:` at :103, before the status write at :100 |
| `get_analysis` | `if not session or not session.analysis` → `404 "Analysis not found"` for *any* id | gate at :321, then child 404 at :323 preserved verbatim |
| `get_transcription` | `if not session or not session.transcription` → `404 "Transcription not found"` | gate at :333, then child 404 at :335 |
| `get_session_tts` | bare `db.get`; synthesized/returned cached bytes for any id | gate at :346, before any text assembly or `synthesize_feedback_audio`; success `FileResponse` and the `503` at :360 unchanged (D-A6/D-A7) |
| `get_feedback` | no session read at all | gate at [feedback.py:26](file:///C:/Users/Sohail/Cadra%20Project/speakflow/backend/app/routes/feedback.py#L26), then `404 "No feedback for session"` for an owned session with no rows (:33) |

Per D-A3 the gate is `owned_session`, not `owned_round_session`: a JAM analysis route stays usable for whichever round the session actually belongs to. Per D-A4, foreign / NULL-owner / never-issued all collapse to the one body `{"detail":"Session not found"}`; a *missing child* on an owned session keeps its own copy. Per D-A2 the resolver is `get_current_user` only — the optional resolver appears nowhere in either module, which the new static guard asserts.

Consumers: of the four GETs, only `POST /analyze` has a live frontend caller (`useAnalyzeSession`, reached from `AnalysisPage` and from `RecordingSession.tsx:67`, the only navigation into the page). `getAnalysis` is imported in `useSessions.ts:11` and used by no hook; `api/feedback.ts`'s `getFeedback` and any `/tts` URL have no reference anywhere in `frontend/src` — so the new 401/404s break no working path `[V]` (grep of the whole frontend source). A visitor can still type `/analysis/<id>` for an arbitrary session, which is why 15.6 covers non-JAM statuses too.

### 15.4 Tests executed — actual results

RED (first run, against the unfixed routes): **86 failed, 20 passed**. Representative demonstrated reasons: `analysis.get / None: expected 401, got 200` (×20 across the four bad-credential shapes and all five handlers); `analysis.get foreign: expected 404, got 200 '{"id":2,"session_id":2,…,"clarity_score":0.0,…}'` — the victim's row, leaked in the refusal's own evidence; the three-leg uniformity check `the three legs differ` (×5); `EP still authorizes with a bare db.get` (×4); `EP does not call owned_session` (×5); `analyze foreign: expected 404, got 200`; `tts cached-file: expected 404, got 200`; `child-less foreign session: denial body is '{"detail":"No feedback for session"}', want '{"detail":"Session not found"}'`.

Two of those 86 were my own plumbing bugs, not security signal, and are itemised in 15.5. After fixing only the plumbing: **82 failed, 24 passed** — the final arrangement was demonstrated RED.

GREEN, after the minimum implementation: `test_analysis_authz.py` **106 passed**. Regressions: AUTH-A `test_auth_fail_closed` **26** + `test_authz_guard_static` **18**; AUTH-B `test_coach_ownership` **74**; AUTH-C `test_session_ownership` **285**; AUTH-E `test_audio_ownership` **141 passed, 1 skipped**. Full backend: **650 passed, 1 skipped, 651 collected** — reconciles against the AUTH-C baseline of 543 (+106 new, +18−15 retarget, −2 narrowed). Frontend: `npm run lint` (`tsc -b`) exit 0 and `npm run build` exit 0 (2603 modules, `✓ built in 4.64s`), both re-run after the final page edit recorded in 15.6.

The suite is behavioural, not status-only: each denial asserts the exact body bytes and content-type, and each refused `/analyze` and `/tts` is snapshotted *after* the owner control (AUTH-C's lesson) so the control's own pipeline calls and clip write are not attributed to the refusal — with a positive control that proves every processor stub is reached, otherwise all the zero-call assertions would be vacuous.

### 15.5 Test-side corrections made during this task (disclosed; none weakens an assertion)

1. **A leak check that could not mean anything** — `assert str(theirs.id) not in json.dumps(rows)` matched the `"2"` inside `created_at: "2026-11-01T17:12:03"` and failed on an owner reading her own single row. Replaced with structural assertions (`{r["session_id"] for r in rows} == {mine.id}`, the victim's id absent from both id columns, content belongs to the caller). Strictly stronger; no assertion removed.
2. **Wrong fixture kwargs** — the child-404 category passed `analysis=/transcription=/feedback=` where the builder takes `with_analysis=` etc.; it raised `TypeError` before reaching its assertion. Fixed to the real parameter names.
3. **A fixture called directly** — `test_valid_token_for_a_deleted_subject_is_rejected` invoked `make_account()` from the test body, so pytest failed it with *"Fixture 'make_account' called directly"* for all five endpoints. **Honest consequence: that category was never demonstrated RED for its security assertion** — it died in plumbing. Fixed by injecting the fixture, and strengthened with a live-subject control leg (200 before the delete, 401 after) so a broken token cannot masquerade as an AUTH-A pass.
   I did **not** re-create the vulnerable state to retro-fit RED for those five cases: `analysis.py` carries pre-existing uncommitted work of its own (the vocal-delivery block at :154-172 and its imports, which are not AUTH-D's), so temporarily restoring an older version risked the user's work for the sake of one redundant proof. What the demonstrated evidence does establish: the handlers bound **no** identity dependency at all (static guards, ×5 RED) and answered **200** to every credential shape tested (×20 RED), which is strictly less strict than the deleted-subject case — so those five could not have passed pre-fix. Label that inference `[I]`, the surrounding 25 cases `[V-live]`.

### 15.6 D-A5 — the analysis page, as implemented

[AnalysisPage.tsx](file:///C:/Users/Sohail/Cadra%20Project/speakflow/frontend/src/pages/AnalysisPage.tsx) previously read `data.status` only, never `analyze.isError`, and fell through to `<AnalysisResults>` — which fills absent metrics with defaults (`overall_score || … || 84`, `speaking_pace || 140`, `duration_seconds || 60`). A 401, 404, timeout or 500 therefore rendered as a *plausible successful report*. The page now renders one of eight states in this order: detail-loading → technical redirect → detail failure → **analysis failure** → processing → recorded failure → pending → **no finished analysis** → report.

- The analysis-failure branch is new: `analyze.isError` returns a `role="alert"` card whose text comes from `describeAnalysisFailure` (401 → sign-in expired, 403/404 → not available for this account, 502/503/504 → service unavailable, no response → connection, `ECONNABORTED` → timeout, else the error message), with two distinct recovery actions — retry the analysis, and `refetch()` the session — the same split D-F drew on the dashboard.
- The report now renders **only** on a server-confirmed `status === "completed"`.
- `pending` is an explicit loading state, because that is what it is on the render before the auto-analysis effect fires; showing it as a failure would flash a false error on the golden path.
- Any other non-completed status (`in_progress` is the live case — `hr.py:74` and `guesstimate.py:78` create sessions with it, and such a id typed into this route used to render the synthetic report) gets an explicit "no finished analysis" card with a user-initiated *Analyze now*, rather than an endless spinner or a fabricated score.
- The auto-trigger effect gained `!analyze.isError` so a refusal is not silently re-issued by a re-render, and no AuthContext rewrite was attempted (D-FE2 stays separate). The successful-report path is unchanged.

Left as-is deliberately: the pre-existing `Failed to load session. It may have been deleted.` card for a failed *detail* query. With AUTH-C that copy now also covers a 401 and a foreign 404, which is imprecise but not a masquerade — changing it is a wording task, not an authorization one.

### 15.7 Working-tree preservation

Branch `feature/hr-round`, HEAD `326d75e5e3c72f930ae39adb2ab3c4e634b0b392` — unchanged; nothing staged (`git diff --cached` empty), `git stash list` still 0. `git status --short` moved from the §14.8 baseline **26 ` M` + 9 `??` = 35** to **28 ` M` + 9 `??` = 37**, and the composition is fully accounted: the two additions are `backend/app/routes/feedback.py` and `frontend/src/pages/AnalysisPage.tsx`, both clean at the baseline; `backend/app/routes/analysis.py` was already ` M` from earlier feature work (its vocal-delivery hunk is *not* AUTH-D's and was not touched) and `docs/` and `backend/tests/` remain single untracked entries whose contents grew by `test_analysis_authz.py` and the fixture additions. No reset, checkout, restore, revert, clean, stash, commit, push, branch switch, dependency install, virtualenv change, migration, server start, browser run or live-database contact was performed.

### 15.8 Verification limits

`[V-live]` for everything in 15.4 — every number came from an executed pytest/tsc/vite run. `[I]` for the deleted-subject RED claim (15.5.3). `[U]` unchanged: PostgreSQL behaviour was not exercised (all evidence is the temp-SQLite harness), no browser verification of the D-A5 states was performed, and no live service was called — the whole suite patches the route-module attributes, so real Whisper, MediaPipe, audEERING, Praat, Ollama and edge-tts were never invoked, which `test_the_stubbed_analysis_processors_replace_the_ones_the_route_imports` pins.

### 15.9 Deferred and out-of-scope (unchanged by this task)

- **D-A9**: `audio_path` / `video_path` still appear in session response bodies; removal needs its own approved change with the consumers.
- **D-A6**: the `/tts` cache key is still `session_{id}_coach.mp3` with no invalidation — an owner who re-analyzes may be served the previous synthesis. Out of scope by decision; the existing `503` behaviour was preserved instead.
- **AUTH-E (#9)**: `GET /api/technical/audio/{filename}` still resolves by filename with no identity dependency, and its tripwire in `test_authz_guard_static.py` still pins that. *(Corrected 2026-11-03: that route is closed — `serve_technical_audio` binds `get_current_user` and resolves through `resolve_technical_audio_path`, the tripwire became the closed-state wiring test at `test_authz_guard_static.py:192`, and the Technical report now fetches its clips with the authenticated player instead of a bare `<audio src>`.)* AUTH-E's browser pass is still outstanding.
- **AUTH-F (#10)**: the `/ws/session/{id}/emotion` handshake carries no authorization. **AUTH-D does not make the live path private.**
- **D-FE2**: no AuthContext rewrite; a 401 still only clears `speakflow_token` in the axios interceptor and leaves redirect to each page.
- **C-07**, **DB-10**, **DB-12**, **H-09/H-10**, **Q2/Q3**, the malformed-`round_metadata` swallow at `sessions.py:149-150` — untouched.

### 15.10 Next task

AUTH-F (#10) — WebSocket handshake authorization — is the last unsecured path in the plan, or AUTH-E's browser verification (#19) if the reviewer wants the `[I]` playback claims promoted to `[V-live]` first. Either way, nothing here is merged: the tree is still uncommitted and staging is the user's call.