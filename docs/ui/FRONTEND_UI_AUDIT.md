# SpeakFlow Frontend — Read-Only UI/UX Audit

**Purpose.** Establish an evidence base for a future professional UI redesign (light theme by default, optional dark mode, persisted preference, consistent SaaS design system, responsive desktop/tablet/mobile). This document plans; it does not implement.

| Field | Value |
| :-- | :-- |
| Audit date | 2026-11-02 |
| Branch | `feature/hr-round` |
| HEAD at audit | `326d75e5e3c72f930ae39adb2ab3c4e634b0b392` |
| Scope | `frontend/` only (source, config, metadata). Backend read only where the UI depends on it. |
| Mode | **Read-only.** No source, config, dependency or documentation file was modified. |
| App started? | **No.** No dev server, no build, no browser. See §10 for what this makes unprovable. |

## Claim labels

Every substantive claim carries one of:

- **[V]** — verified by reading the current working tree (or the installed dependency's own resolved config / compiled output). Includes file:line.
- **[I]** — inferred from [V] evidence; reasonable but not directly proven.
- **[U]** — unverified; requires running the app, a browser, or the backend.

No **[V-live]** claims appear in this document, because nothing was executed in a browser.

---

## 1. Architecture inventory

### 1.1 Stack [V]

| Concern | Finding | Evidence |
| :-- | :-- | :-- |
| Framework | React 18.2, TypeScript 5.3, `react-jsx` transform | `frontend/package.json:13-14`, `frontend/tsconfig.json:12` |
| Build | Vite 5.0.7, `@vitejs/plugin-react` 4.2.1 | `frontend/package.json:30`, `frontend/vite.config.ts:5` |
| Styling | Tailwind CSS 3.4.19 installed via PostCSS + Autoprefixer | `frontend/package.json:28-29`, `frontend/postcss.config.js:2-5` |
| Routing | `react-router-dom` 6.20, declarative `<Routes>` | `frontend/src/App.tsx:41-66` |
| Server state | `@tanstack/react-query` 5.13 — **wired but nearly unused** (§1.5) | `frontend/src/main.tsx:8-24`, `frontend/src/hooks/useSessions.ts` |
| Client state | React Context (`AuthProvider`) + local `useState` | `frontend/src/context/AuthContext.tsx` |
| HTTP | Single axios instance + request/response interceptors | `frontend/src/api/client.ts:7-32` |
| Charts | recharts 2.10 (5 files) + hand-written inline SVG | `frontend/src/components/Dashboard/*`, `Analysis/MetricsChart.tsx` |
| Motion | framer-motion 10.16 — used in only 4 files | `Analysis/FeedbackSection.tsx`, `Analysis/TranscriptionView.tsx`, `Recording/FaceTrackingOverlay.tsx`, `Recording/RecordingSession.tsx` |
| Icons | **Two systems.** Material Symbols webfont (281 sites, 21 files) and lucide-react (9 files) | `frontend/index.html:15-18`, `frontend/src/index.css:22-36` |
| Fonts | Inter, Plus Jakarta Sans, JetBrains Mono + Material Symbols, all from Google Fonts CDN | `frontend/index.html:9-18` |
| Tests | **None.** `lint` script is `tsc -b` only | `frontend/package.json:6-11` |
| Size | One JS chunk 1,159,047 B + one CSS 67,019 B in the last build | `frontend/dist/assets/` (dated Nov 1, untracked) |

The Tailwind *spec* pin in `package.json` is `^3.3.6` while the installed artifact is `3.4.19`. [V] All utility-generation results in §5.2 were measured against the **installed 3.4.19**, not against documentation.

### 1.2 Layout of source [V]

56 TypeScript/TSX/CSS files, 14,741 lines. Largest: `components/Analysis/AnalysisResults.tsx` (1,275), `pages/technical/TechnicalStudio.tsx` (901), `pages/guesstimate/GuesstimateReport.tsx` (863), `pages/guesstimate/GuesstimateStudio.tsx` (818), `pages/hr/HRReport.tsx` (730), `pages/hr/HRStudio.tsx` (717).

### 1.3 Dead / abandoned infrastructure [V]

Four pieces of configured infrastructure are referenced nowhere:

1. **`@` path alias** — defined in `frontend/vite.config.ts:8-10` and `frontend/tsconfig.json:19-21`; **0** imports use it. Every module is reached by `../` chains.
2. **Custom spacing scale** — 9 tokens (`space-xs…space-xl`, `gutter`, `gutter-mobile`, `margin`, `margin-mobile`) in `frontend/tailwind.config.js:56-66`; **0 usages**. I proved these *would* work: compiling the project's own config emits `.p-space-xs`, `.p-gutter`, `.m-margin`. So this is dead config, not broken config.
3. **`components/Layout/Sidebar.tsx` and `components/Layout/Header.tsx`** — no file imports them (§4.1).
4. **`useLiveEmotionStream`'s `isConnected`** — returned at `frontend/src/hooks/useLiveEmotionStream.ts:339`; no consumer destructures it (§6.3).

### 1.4 What to reuse in the redesign

Everything already installed is reusable; **no new dependency is required for theming.** Tailwind v3 consumes CSS variables directly, so a light/dark token layer is a config + CSS change, not a library change.

| Keep | Reason [V] |
| :-- | :-- |
| Tailwind 3.4 | Already the styling substrate; token layer slots in without migration |
| react-router-dom 6 | Route table is coherent and small (`App.tsx:41-66`) |
| react-query 5 | Already installed and correctly configured; only *adoption* is missing |
| recharts 2 | 5 chart files depend on it; replacement has no justification |
| framer-motion 10 | Only 4 files; keep, do not expand |
| axios | One interceptor seam (`client.ts:12-22`) is exactly what auth needs |
| Material Symbols | 281 call sites; the dominant system (see open question Q2) |
| Inter / Plus Jakarta Sans / JetBrains Mono | Already loaded; the type role tokens in `tailwind.config.js:67-79` map onto them cleanly |

**The one place a new dependency has a concrete reason:** the app contains **zero** dialog, tab, listbox or disclosure semantics (`role="tab"` = 0, `role="dialog"` = 0, `<table>` = 0, `onKeyDown`/`Escape`/`tabIndex` = 0 anywhere). If the redesign wants accessible modals/tabs/menus without hand-writing keyboard logic, a headless primitive library is the cheapest path. **This is a decision for the user, not a recommendation to act on** — see Q8.

---

## 2. Route and page inventory

### 2.1 Route table [V]

All routes except `/login` render inside one protected `<Layout />` element (`App.tsx:43-65`).

| # | Path | Component | Purpose |
| :-- | :-- | :-- | :-- |
| 1 | `/login` | `pages/AuthPage.tsx` | Standalone sign-in / register; **not** inside Layout |
| 2 | `/` | `pages/HomePage.tsx` | "Practice Arena" — mode hub + presets |
| 3 | `/record` | `pages/RecordingPage.tsx` | JAM live recording (thin wrapper over `RecordingSession`) |
| 4 | `/technical` | `pages/technical/TechnicalStudio.tsx` | Technical drill setup + live round |
| 5 | `/technical/:sessionId` | same | Resume an existing technical session |
| 6 | `/technical/report/:sessionId` | `pages/technical/TechnicalReport.tsx` | Technical evaluation dossier |
| 7 | `/guesstimate` | `pages/guesstimate/GuesstimateStudio.tsx` | Guesstimate setup + live round |
| 8 | `/guesstimate/:sessionId` | same | Resume |
| 9 | `/guesstimate/report/:sessionId` | `pages/guesstimate/GuesstimateReport.tsx` | Placement-cell dossier |
| 10 | `/hr` | `pages/hr/HRStudio.tsx` | HR/STAR setup + live round |
| 11 | `/hr/:sessionId` | same | Resume |
| 12 | `/hr/report/:sessionId` | `pages/hr/HRReport.tsx` | Behavioral dossier |
| 13 | `/analysis/:sessionId` | `pages/AnalysisPage.tsx` | JAM analysis (Whisper/DSP results) |
| 14 | `/dashboard` | `pages/DashboardPage.tsx` | Placement readiness + progress |
| 15 | `/settings` | `pages/SettingsPage.tsx` | API URL + model overrides |
| 16 | `*` | → `Navigate to="/"` | Catch-all |

**No page was assumed.** Each row above is a `<Route>` literal in `App.tsx:42-64`. There is no profile route, no reports index route, and no onboarding route — those categories simply do not exist as pages. `Profile` exists only as an avatar+name+email cluster in the header (`Layout.tsx:173-194`) and `Settings` contains no profile fields at all (`SettingsPage.tsx:29-66`).

### 2.2 Navigation defects [V]

- **`/settings` is unreachable through the UI.** Its only links live in the two orphaned components (`Layout/Sidebar.tsx:8`, `Layout/Header.tsx:8`). The live nav is `Layout.tsx:10-17`, which lists `/`, `/record`, `/technical`, `/guesstimate`, `/hr`, `/dashboard`. Reachable only by typing the URL. [V]
- **`/dashboard` is linked once, `/settings` zero times** in live code. [V]
- **SPA route rendered as a hard anchor:** `components/Dashboard/GuesstimateProgressDashboard.tsx:423-429` and `:498` use `<a href={\`/guesstimate/report/${id}\`}>` instead of `<Link>`. Clicking forces a full document reload, discarding the SPA. [V]
- `/analysis/:sessionId` is reached only programmatically (`RecordingSession.tsx:67`) and from history (`SessionHistory.tsx:118`). `AnalysisPage.tsx:59` can further redirect to `/technical/report/:id`. [V]

### 2.3 Page section maps [V]

Sections below are the render order as labelled by the authors' own `{/* … */}` comments, which I extracted per file. They are the natural redesign work-breakdown units.

#### `/` HomePage (547 lines) — "Practice Arena"
Hero title deck → Quick Stats telemetry strip → 4-column mode hub (Technical / HR / Guesstimate / JAM), each with its own hand-drawn SVG "visual telemetry" (Logic Mesh, STAR Quadrants, Decomposition Tree, Wave Burst) and focus-metric tags → bottom split: Recommended AI Challenge deck + Arena Presets (persona switcher, metronome/cadence slider, Audio Hardware Status, Optical Mesh Sensor Status).
Data: `api/guesstimate`, `api/coach`, `api/technical`, direct `useState`; writes `verbaliq_preset_persona` / `verbaliq_preset_wpm` to localStorage (`HomePage.tsx:35-36`).
Problems: the "Audio Hardware Status" block (`HomePage.tsx` ~`{/* Audio Hardware Status */}`) asserts *"Lossless Acoustic Input / 48kHz Low Latency / Calibrated"* and "Optical Mesh Active" as **static strings** — nothing queries a device. [V] For face tracking, `useFaceTracking` only ever runs inside `RecordingSession.tsx:43-46`, so the HomePage badge claims activity where none is happening. [V]

#### `/dashboard` DashboardPage (330 lines) — "Performance Hub"
Banner → **Layer 1** Placement Readiness Matrix → Autonomous Curriculum Coach Agent card → stats strip → **Layer 2** round-specific diagnostics with 5 filter tabs (all/jam/technical/guesstimate/hr) → **Layer 3** drill-down session history.
Data: `hooks/useSessions` progress queries + `api/coach`.
Problems: filter tabs are hand-rolled `useState` (`DashboardPage.tsx:41`, `:190-235`) with no tab semantics. [V]

#### `/record` RecordingPage (21 lines) + `RecordingSession.tsx` (185)
Header copy → TopicSpinner → video preview → LiveConfidenceNeedle → RecordingControls. Reads `?topic=` via `useSearchParams` (`RecordingSession.tsx:18`). This is the highest-risk surface in the app (§6.4).

#### `/analysis/:sessionId` AnalysisPage (128) → `AnalysisResults.tsx` (1,275)
Loading/error branches (`:55`, `:91`, `:108`) then the monolith: score hero, cadence, radar polygon, filler analysis, authenticated audio player with seek, transcript, `VocalDeliveryCard`, feedback, `window.print()` export (`:409`).

#### `/technical`, `/guesstimate`, `/hr` — three Studios (901 / 818 / 717)
Structurally the **same page twice-and-a-half**: ambient aura → breadcrumb header → left config column (steps, pills, chips) → right launch column → then, once `sessionId` exists, studio header strip → stepper & timer → question card deck → guidance/roadmap → articulation textarea + scratchpad → action strip. [V]
Differences are content, not layout: Technical adds RAG resume ingestion with a hidden `<input type=file ref={fileInputRef}>` (`TechnicalStudio.tsx:623-630`, `.click()` at `:681`); Guesstimate adds the 4-step consulting roadmap + `LiveCoachNudge` (`:773`); HR adds STAR hints + track selection.
Each independently re-implements: SpeechRecognition, MediaRecorder, TTS, timer, localStorage resume key, and the aura block. [V]

#### `/*/report/:sessionId` — three Reports (612 / 863 / 730)
Shared skeleton: injected print stylesheet → aura → breadcrumb + action buttons → hero score + pillars → per-question tabs/accordion → transcript + audio player → diagnostics → model script + TTS → aggregate summary. [V]
Divergence: only `GuesstimateReport.tsx:102-121` sets `@page { size: A4 }` and `print-color-adjust: exact`; `HRReport.tsx:107` and `TechnicalReport.tsx:126` do not. Identical features, different print fidelity. [V]

#### `/login` AuthPage (220) and `/settings` SettingsPage (69)
AuthPage duplicates AuthModal's form (brand header, tab toggle, alert box, form body). SettingsPage is a two-field form (API URL, model) with a 1.5 s "Preferences Saved" toast via `setTimeout` (`:19`).

### 2.4 Visual problems, per page — with evidence

| Problem | Evidence |
| :-- | :-- |
| **SettingsPage renders the wrong theme.** It is written entirely in light tokens — `text-slate-900`, `bg-slate-50`, `border-slate-200`, `text-slate-800` inputs, `focus:ring-violet-500`, `text-emerald-600 bg-emerald-50` toast — while the live app is dark. [V] `SettingsPage.tsx:25-26,35,49,61` |
| `violet-500` is the **abandoned brand accent** (see §4.1), still used as the only real focus ring in the app. [V] `SettingsPage.tsx:35,49` |
| **Three product names in one product.** "VerbalIQ" (12 sites incl. browser title, sidebar logo, auth CTA, `types/index.ts:83` `VerbalIQReport`), "SpeakFlow" (45 sites), "InterviewForge" (1). `GuesstimateReport.tsx:131` prints "SpeakFlow Campus Placement Analytics" under chrome that says VerbalIQ. [V] |
| **Fabricated telemetry presented as live status.** Sidebar "Cognitive Load — Optimal 42%" with `style={{ width: "42%" }}` (`Layout.tsx:104-111`), "Engine Status: Online" (`:116-120`), "14 Days Streak" (`:167`), "Tier 3 Candidate" (`:151`), "AI Coach v2.4" (`:50`), "Adaptive JAM & Technical" (`:146`). [V] None of these derive from data. I confirmed no `streak` field exists in the frontend types (`types/index.ts:182-193`) **or** in `backend/app/routes/progress.py`. So it is not "unwired real data" — there is no source to wire. [V] |
| **Sub-legible type.** 213 instances of `text-[9px]`/`text-[10px]` across the app. [V] |
| **Emoji as UI.** 29 emoji/dingbat glyphs used as icons, e.g. `Layout.tsx:165` 🔥 for streak. [V] |
| **Light-mode chips inside dark cards.** `MetricsChart.tsx:231,235,262,282-285,344,348,359,369` use `bg-emerald-50 text-emerald-700 border-emerald-200` etc. [V] |
| **Duplicate aura block, 11 times in 9 files.** The same two `w-[700px]`/`w-[500px]` blurred gradient divs are pasted into HomePage, AuthPage, all three Studios and all three Reports. [V] e.g. `HomePage.tsx:48-49`, `HRReport.tsx:124-125`, `TechnicalStudio.tsx:380-381,763-764` |

### 2.5 Responsive behaviour [V]

| Breakpoint | Occurrences |
| :-- | :-- |
| `sm:` | 186 |
| `md:` | 32 |
| `lg:` | 39 |
| `xl:` | 5 |
| `2xl:` | 0 |

- The strategy is effectively **binary mobile/desktop**, keyed on `sm` (640 px). There is no tablet-specific composition, and `2xl` is unused. [V]
- **15 files contain no breakpoint prefix at all**, including `AnalysisPage.tsx`, `RecordingControls.tsx`, `VideoPreview.tsx`, `ProtectedAudioPlayer.tsx`, `TopicSpinner.tsx`, `FaceTrackingOverlay.tsx`, `SentenceAnalysis.tsx`, `ProgressDashboard.tsx`, `LiveCoachNudge.tsx` and the three Common primitives. [V]
- Content is **clipped, not scrolled**: 47 `overflow-hidden` vs 2 `overflow-x`. Wide tables/charts get cut off rather than made pannable. [V]
- Fixed-width decorative/functional elements exist: `w-[700px]` ×11, `w-[500px]` ×11, `min-w-[210px]` ×4. [V]
- The shell is `fixed` sidebar `w-72` + `md:pl-72` + `fixed` header + `pt-16` on `<main>` (`Layout.tsx:30-33,126-128,209`). [V] User identity collapses to an avatar below `xl` (`:178`).
- Global `::-webkit-scrollbar { display: none }` (`index.html:27-29`) hides scrollbars on every scroll container. [V] — a deliberate choice that removes a scroll affordance.
- The mobile drawer backdrop is a plain `<div onClick>` (`Layout.tsx:22-27`) with no role, no keyboard dismissal. [V]

### 2.6 Recommended future improvements per page

Ordered by payoff, all design-only:

1. **Extract `<PageShell>` + `<AmbientBackdrop>`** — deletes 11 duplicated aura blocks and standardises the breadcrumb/action row all three reports repeat.
2. **Extract a `<StudioLayout>`** for the three Studios; the setup→live two-state page shape is identical three times.
3. **Extract `<ReportDossier>`** with named slots; move the print rules to one global stylesheet.
4. **Give Settings a real IA** — currently 2 fields and no nav entry; it should host the theme toggle, sign-out and profile summary.
5. **Replace fabricated shell telemetry** with real `ProgressSummary` values (which already include `avg_eye_contact` and `avg_posture_quality`, `types/index.ts:188-189`) or remove it. See Q3.
6. **Convert tab/filter/dismiss UI** to accessible components (§1.4, Q8).
7. **Add tablet composition** at `md`/`lg`, not just `sm`.

---

## 3. Shared component inventory

### 3.1 What exists [V]

| Category | Status | Location |
| :-- | :-- | :-- |
| App shell | 1 live + 2 orphaned | `Layout/Layout.tsx` (216) |
| Card | **1 primitive, well adopted** | `Common/Card.tsx` — imported by 14 files, `<Card` used 29× |
| Button | **primitive exists, nearly ignored** | `Common/Button.tsx` — imported by 3 files, `<Button` 10× |
| Loading | 1 primitive, 4 usages | `Common/Loading.tsx` — `AnalysisPage` ×3, `DashboardPage` ×1 |
| Modal | 1, app-specific | `Auth/AuthModal.tsx` (225) |
| Charts | 5 recharts files + inline SVG | `Analysis/MetricsChart.tsx`, `Dashboard/*ProgressDashboard.tsx` |
| Audio player | 1 authenticated primitive + 3 ad-hoc paths | `Recording/ProtectedAudioPlayer.tsx` (173) |
| Status badge / pill | **none** — inline everywhere | §3.3 |
| Tabs | **none** — 4 independent hand-rolls | §3.4 |
| Table | **none.** `<table>` appears 0 times in the app | [V] |
| Form field | **none.** 18 `<input>`, 5 `<textarea>`, 2 `<select>`, 23 `<label>` — all inline | [V] |
| Progress bar | **none.** 12 inline `style={{width/height}}` bars in 10 files | [V] §3.2 |
| Empty state | **none** — ad-hoc per page | [V] |
| Error notice | **none.** 8 files keep their own `setError` state; `describeAudioError`, `describeAnalysisFailure` are local formatters | [V] |
| Toast/notification | none (SettingsPage's inline `setTimeout` span is the only transient) | [V] `SettingsPage.tsx:19-64` |
| Recording controls | 1 | `Recording/RecordingControls.tsx` (128) |
| Live HUD | 3 | `Interview/LiveConfidenceNeedle`, `LiveCoachNudge`, `VocalDeliveryCard` |

### 3.2 Progress bars — 12 reimplementations [V]

`Analysis/MetricsChart.tsx:210`, `Analysis/AnalysisResults.tsx:727`, `technical/TechnicalReport.tsx:247`, `Interview/VocalDeliveryCard.tsx:156,328`, `hr/HRReport.tsx:229,254,279`, `Recording/RecordingControls.tsx:74`, `Layout/Layout.tsx:110`, `Dashboard/TechnicalProgressDashboard.tsx:520`, `guesstimate/GuesstimateReport.tsx:727`.
Each independently chooses track colour, height, radius and label treatment; only `GuesstimateReport.tsx:727` clamps (`Math.max(15,…)`) and only `TechnicalReport.tsx:247` clamps both ends (`Math.min(100, Math.max(0, …))`). [V] The rest can render negative or >100 % widths if the API returns out-of-range scores. [I]

### 3.3 Semantic status colour — re-derived on every page [V]

The same traffic-light verdict is hand-computed with inconsistent opacity conventions:

- `guesstimate/GuesstimateReport.tsx:90-96` → `text-rose-400 bg-rose-500/10 border-rose-500/20`
- `GuesstimateReport.tsx:540-546` → `bg-{emerald,rose,amber}-500/15`
- `GuesstimateReport.tsx:563-567` → per-evidence-type badge with icon
- `GuesstimateReport.tsx:424-426` → `-400/15`
- `Analysis/MetricsChart.tsx:282-285` → `text-emerald-700 bg-emerald-50 border-emerald-200` (**light** chips)
- `Interview/LiveConfidenceNeedle.tsx:19-58` → a `BANDS` table with **inline hex** gradient stops `#34d399 #10b981 #fbbf24 #60a5fa #fb7185 #f97316`

Five different treatments for "good / middling / bad", three of which only exist because the author needed a chip. This is the clearest missing primitive: **`<StatusBadge tone="positive|caution|negative">`**.

### 3.4 Tabs — 4 independent implementations, none accessible [V]

`DashboardPage.tsx:41,190-235` (5-way round filter) · `GuesstimateProgressDashboard.tsx:26,143-157` (primary/four-rubrics) · `hr/HRReport.tsx` ("Multi-Question Selector Tabs") · `pages/AuthPage.tsx` ("Tab Toggle" login/register). Zero `role="tab"`, zero `aria-selected`, zero keyboard handling. [V]

### 3.5 Duplication summary

| Duplicated thing | Times | Files |
| :-- | :-- | :-- |
| Ambient aura background | 11 | 9 |
| Injected `@media print` stylesheet | 3 | 3 report pages |
| Progress bar | 12 | 10 |
| Status/verdict badge | 5+ | 4 |
| Tabs | 4 | 4 |
| Auth form (login+register) | 2 | `AuthPage.tsx`, `AuthModal.tsx` |
| Studio page skeleton (setup+live) | 3 | 3 studios |
| Report dossier skeleton | 3 | 3 reports |
| SpeechRecognition + MediaRecorder + TTS plumbing | 3 | 3 studios |
| Form-field class string | 22 | 10 |

### 3.6 Reuse opportunity ranking

Highest value, lowest risk: `<AmbientBackdrop>`/`<PageShell>` → `<StatusBadge>` → `<ProgressBar>` → `<Tabs>` → `<FormField>`/`<Input>` → `<Tabs>` → `<Modal>` → `<EmptyState>`/`<ErrorNotice>` → `<AudioPlayer>` (see §6 — this one is *not* low risk).

---

## 4. Current design assessment

### 4.1 Two abandoned generations are still on disk [V]

`components/Layout/Header.tsx` is a complete **light theme** implementation — `bg-white`, `border-slate-200/80`, `from-violet-600 to-fuchsia-600`, `bg-violet-50 text-violet-700` — branded **"InterviewForge"** (`:22`). `components/Layout/Sidebar.tsx` is a dark nav branded with generic labels, using `bg-surface-950/40`, `bg-primary-600/20`, `text-primary-200`.

Neither is imported by any file (§1.3). [V] Together with SettingsPage's light tokens (§2.4) and the `violet` accent, they are strong evidence the app has already been through at least one partial light-theme attempt that was abandoned mid-way. **[I]** for the "abandoned mid-way" narrative; **[V]** for the files, brand strings and non-adoption.

**Consequence for the redesign:** these two files are the most useful artefacts in the repo for a light theme — they show what a prior light pass looked like — but they are also dead code referencing tokens that do not exist. Decide explicitly: revive, or delete. Do not let them survive as a third half-state.

### 4.2 Retain [V]

- **The semantic token vocabulary.** `tailwind.config.js:7-55` names colours by *role* (`surface`, `surface-container-low`, `on-surface`, `outline-variant`, `primary-container`), Material-Design-3 style. This is the correct abstraction for a light/dark system and already covers 51 tokens. Retain the names; re-point the values.
- **Font role tokens.** `fontFamily` maps headline/body/label roles onto three families (`tailwind.config.js:67-79`) and sees 514 uses. [V] Good bones.
- **Two real animations** (`fade-in`, `slide-up`, `tailwind.config.js:80-93`) — restrained.
- **The `<Card>` primitive** — 29 uses, genuinely shared. [V]
- **Monospace for numerics** (`label-numeric*`) — a good convention to keep.
- **`<ProtectedAudioPlayer>`'s care** — it is the most rigorously engineered component in the app (generation guards, explicit teardown, "player-element-missing" publishing). Styling must not disturb it. [V]

### 4.3 Redesign [V]

| Aspect | Verdict | Evidence |
| :-- | :-- | :-- |
| Colour consistency | **Fails.** Two parallel palettes: 47 role tokens + 471 raw Tailwind palette classes (`amber` 105, `emerald` 99, `rose` 94, `slate` 70, `violet` 31, +9 families), plus 114 hex literals in 10 files. | `tailwind.config.js:7-55`; counts via grep |
| Typography hierarchy | **Fails.** No `fontSize` key exists in the theme at all ([V]: resolved config has only Tailwind defaults). Sizing is 663 `text-[Npx]` arbitrary values across **16 distinct pixel sizes** vs 673 default-scale uses. `fontFamily` encodes *role*, `fontSize` encodes nothing. | `tailwind.config.js:67-79`; counts |
| Spacing | **Fails.** 9 custom spacing tokens defined, 0 used; 358 uses of `p-*-3.5`-style half-steps. | `tailwind.config.js:56-66` |
| Radius consistency | **Mixed.** `rounded-full` 202 / `rounded-lg` 189 / `rounded-xl` 183 / bare `rounded` 109 / `rounded-md` 9 / `rounded-xs` 4 (**invalid**, §5.3). No `borderRadius` extension in theme. | counts |
| Shadow consistency | **Fails.** 8 named sizes used together (`md` 47, `lg` 43, `sm` 41, `xl` 21, `xs` 3 **invalid**, `inner` 2, bare 6) + 9 arbitrary `shadow-[…]` + coloured brand shadows (`shadow-primary` 10, `-secondary` 6, `-tertiary` 5, `-error` 2, `-violet` 1). | counts |
| Visual density | **High.** Default `text-xs`/`text-[10px]`/`text-[11px]` dominates; report pages stack hero + pillars + tabs + accordions + summaries in one scroll. | §2.3 |
| Navigation clarity | **Fails.** `/settings` unreachable, 2 routes rendered as hard `<a>`, no breadcrumb component though 6 pages hand-write one. | §2.2 |
| Information hierarchy | **Uneven.** Reports have deliberate "Priority 2/3/4" ordering ([V] `GuesstimateReport.tsx` comments) but the shell competes with fake telemetry (§2.4). | |
| Accessibility | **Fails broadly** (§4.4). | |
| Responsive | **Binary, tablet-blind** (§2.5). | |

### 4.4 Accessibility findings [V]

| Finding | Count / evidence |
| :-- | :-- |
| Zero keyboard interaction app-wide: `Escape`, `onKeyDown`, `tabIndex` | **0 occurrences** in all `.tsx` |
| `aria-*` attributes total | **7** across 56 files |
| `role=` attributes total | **8** (mostly `role="status"`/`"alert"` in `ProtectedAudioPlayer.tsx:161-170`) |
| Form labels programmatically associated | **0 `htmlFor`** against 18 inputs + 23 `<label>` |
| Focus visibility removed and replaced | 22 `focus:outline-none`; all 22 add *some* `focus:` style, but **17 replace it with a border-colour change only** (`focus:border-secondary`/`-primary`), 5 add a ring. `focus-visible` = **0** uses. |
| Dialog semantics | none: `role="dialog"`/`aria-modal`/`<dialog>` = 0; `AuthModal.tsx:66` dismisses via `<div className="fixed inset-0 -z-10" onClick>` |
| Disclosure semantics | `TechnicalReport.tsx:372,408` accordion buttons carry no `aria-expanded` |
| Colour-only meaning | the entire traffic-light system (§3.3) plus `LiveConfidenceNeedle`'s bands; label text usually accompanies it, which mitigates [I] |
| Sub-11 px text | 213 occurrences |
| Scroll affordance removed | `index.html:27-29` |
| Error boundary | **none** — `ErrorBoundary`/`componentDidCatch`/`Suspense`/`lazy` all 0. Combined with an unguarded `JSON.parse` in the auth boot path (`AuthContext.tsx:24`), one corrupt `speakflow_user` localStorage value crashes render with a blank page. [V] for the code; **the blank-page symptom is [U]** (not executed) |

Note the honest limit: `[V]` here means "the markup/attributes are absent", which is a source-level fact. WCAG pass/fail is a rendering-level judgement I have not tested. **[U]**

---

## 5. Theme audit

### 5.1 How dark is implemented today [V]

The dark theme is **not a theme**. It is the only palette, baked three ways:

1. `frontend/index.html:2` — `<html class="dark" lang="en">`, hardcoded, never changed by any code.
2. `frontend/src/index.css:6-8` — `:root { color-scheme: dark; }`, hardcoded.
3. `frontend/tailwind.config.js:7-55` — 51 colour tokens whose **values are literal dark hex**, e.g. `surface: "#10131a"`, `on-surface: "#e1e2ec"`, `outline-variant: "#464554"`.

So the `darkMode: "class"` setting (`tailwind.config.js:3`) is configured but inert: the class is permanently on, and — the decisive point — **`dark:` appears exactly once in the entire codebase**: `components/Technical/SentenceAnalysis.tsx:129`, `text-rose-600 dark:text-rose-300`. [V]

### 5.2 Centralisation and tokens [V]

| Question | Answer |
| :-- | :-- |
| Are colours centralised? | **Half.** 51 named role tokens exist and are widely used (this is the app's biggest asset). But their *values* live in JS, not CSS. |
| Do CSS variables exist? | **No.** `var(--…)` appears **0** times in `src`. One `--*:` declaration exists, and it is the Material Symbols font-variation property inside `index.css:22-36`. [V] |
| Is theme persisted? | **No.** 27 `localStorage` sites exist, all for auth/model/session-resume/JAM presets. No theme key, no `matchMedia`, no `prefers-color-scheme`, no `documentElement.classList` anywhere. [V] |
| System-theme integration? | **Absent.** [V] |
| Is there a ThemeProvider? | **No.** The only provider pair is `AuthProvider` + `QueryClientProvider` (`main.tsx:19-23`). [V] |

This matters for effort estimation: because values are static hex in `tailwind.config.js`, **adding a `.dark` class or a `data-theme` attribute changes nothing.** Every token must first be re-pointed at a CSS variable before a toggle can work. [V] — this is the single structural prerequisite of the whole redesign.

### 5.3 Invalid utilities — proven by the installed compiler, not by documentation [V]

I compiled the project's own Tailwind config with its own installed PostCSS/Tailwind (3.4.19) and inspected the emitted CSS. The probe used `content: [{ raw: … }]` and wrote only to the OS temp directory; the workspace was untouched.

**No CSS is emitted** (these class names are dead in the running UI):

| Class | Used at | Impact |
| :-- | :-- | :-- |
| `btn-danger` | `Common/Button.tsx:13` | `.btn-danger` is not defined in `index.css` (only `:43` `.btn-primary`, `:49` `.btn-ghost`) |
| `rounded-xs` | `HomePage.tsx:203-206` (4) | minor — decorative equaliser bars |
| `shadow-xs` | `FeedbackSection.tsx:60`, `Header.tsx:15`, `RecordingControls.tsx:71` (3) | minor |
| `backdrop-blur-xs` | `MetricsChart.tsx:71,104` (2) | minor |
| `border-primary-500`, `border-t-primary-400` | `Common/Loading.tsx:8` | **spinner colour never applies** |
| `bg-primary-600`, `text-primary-200`, `bg-surface-950` | `Layout/Sidebar.tsx:13,22` | dead file anyway |

Root cause for the numeric ones: `primary` is declared as a **flat string** (`tailwind.config.js:54`), so no `primary-200…600` scale exists. [V]

Two of these are real, visible defects, and they are the two most-used primitives:

- **DEF-1 — the Stop button is unstyled.** `variantClass.danger` resolves to a class that emits nothing (`Button.tsx:13`), and `variant="danger"` **is** used — on the **Stop recording** control, `RecordingControls.tsx:110`. It therefore receives no padding, no background, no radius. [V] for the class chain; the on-screen result is **[U]**.
- **DEF-2 — the loading spinner has no ring colour.** `Loading.tsx:8` asks for `border-primary-500/30` + `border-t-primary-400`; both are dead, so all four edges fall back to `currentColor` from `text-slate-300` on the parent (`:7`) — a uniform ring, which cannot show rotation. `Loading` is used on both primary async surfaces (`AnalysisPage.tsx:55,91,108`, `DashboardPage.tsx:51`). [V] for the code; **[U]** visually.

Control results from the same compile confirm the probe is sound: `rounded-lg`, `shadow-md`, `backdrop-blur-sm`, `bg-surface`, `bg-slate-50`, `bg-amber-500`, `p-space-xs`, `p-gutter`, `.p-3\.5`, `.text-\[9px\]`, `.w-\[700px\]`, `.bg-primary\/10` **all generated**. [V]

### 5.4 Third-party theming [V]

- **recharts** — colours are passed as props/hex, not classes: 99 hex-bearing lines concentrated in `TechnicalProgressDashboard.tsx` (38), `GuesstimateProgressDashboard.tsx` (24), `ProgressDashboard.tsx`/`HRProgressDashboard.tsx` (9 each), `MetricsChart.tsx` (6). Chart axes/grid/tooltip are also dark-styled inline. A CSS-variable theme **will not reach them** — they need an explicit JS token lookup. [V] for the props; [I] for "will not reach".
- **Icons** — Material Symbols is an icon *font* and inherits `currentColor` (`index.css:22-36`), so it themes automatically. **[I]** (font-inheritance behaviour, not rendered here).
- **SVG gauges/polygons** — theme-unreachable by CSS: `LiveConfidenceNeedle.tsx:28-31,42-43,56` inline `stopColor` hex + `stroke-*` classes; `AnalysisResults.tsx:228-236` radar `points` math; `:278-285` sparkline. [V]
- **Print** — the three injected stylesheets force `background: white !important; color: #111 !important` and hide `nav, aside, header, audio, button`. Pages additionally carry `print:text-black`, `print:border-black/20`. **This proves the app currently needs an override layer to exist on paper** — a light-first token system absorbs most of it. [V]

### 5.5 Recommended light-first architecture (proposed, not implemented)

**Prerequisite, in this order:**

1. **Move values into CSS variables, keep Tailwind token names.** Define `--surface`, `--on-surface`, `--outline-variant`, … in `:root` with **light** values; redefine under `[data-theme="dark"]`. Point each Tailwind colour at its variable (`surface: "var(--surface)"`), replacing the 47 literal hex values in `tailwind.config.js:7-55`. No plugin needed.
2. **Stop hardcoding the theme.** Remove `class="dark"` from `index.html:2`; make `color-scheme` follow the token (`color-scheme: light dark` in `index.css:6-8`).
3. **Add a `ThemeProvider`.** Mirror the existing `AuthProvider` shape (`context/AuthContext.tsx`) for consistency. Set `document.documentElement.dataset.theme`; keep the context value minimal (`theme`, `setTheme`, `resolvedTheme`).
4. **Prevent a first-paint flash.** Inline a tiny pre-hydration script in `index.html` `<head>` that reads the stored preference and sets `data-theme` before CSS paints. This is the reason the provider cannot be React-only. **[I]** — standard hydration-flash reasoning, unverified in this app.
5. **Persist + follow the system.** Key `speakflow_theme` (aligns with the existing `speakflow_*` namespace, `client.ts:13,17`). Values `"light" | "dark" | "system"`; `matchMedia("(prefers-color-scheme: dark)")` supplies the `system` resolution and a listener reacts to live changes.
6. **Tone tokens for semantics.** Promote the de-facto status palette to first-class tokens — `--success`, `--warning`, `--danger`, `--info` + their container/on-container pairs — so §3.3's five hand-rolled badges collapse into `<StatusBadge tone=…>`.
7. **Give charts a JS token bridge.** A `useChartTheme()` returning the current hex set (via `getComputedStyle` on a hidden probe, or a single exported `tokens[theme]` map) fed into recharts `stroke`/`fill`/`stopColor`. Charts cannot be themed by CSS alone (§5.4).
8. **Fix the 8 invalid utilities** while touching each file — but note DEF-1/DEF-2 sit in `Common/`, which the redesign is replacing anyway; they need not block anything.

**Design-token structure** (proposed):

```
tokens/
  color.light.css   :root          — surfaces, content, borders, brand, tone
  color.dark.css    [data-theme]   — same names, dark values
  typography.css    — role scale: display / headline-lg|md|sm / body-lg|md|sm / label-caps / label-numeric
                      each with size + line-height + letter-spacing, replacing the 16 arbitrary px values
  spacing.css       — 4/8/12/16/24/32/40/48 ; adopt or delete the 9 dead tokens (§1.3)
  radius.css        — sm/md/lg/xl/full (collapse 5 current treatments)
  elevation.css     — sm/md/lg only (collapse 8 named + 9 arbitrary + 5 brand shadows)
```

**Shared component architecture** (proposed): keep `components/Common/` as the primitive home (it already exists and `Card` is adopted); add `Badge`, `Tabs`, `Modal`, `ProgressBar`, `FormField`, `EmptyState`, `ErrorNotice`, `StatusPill`, `AmbientBackdrop`, `PageShell`. **Do not** add a component library — the existing `Card`/`Button` pattern (thin wrapper + class merge, `Card.tsx:7-18`) is adequate and has no dependency cost.

**Application shell:** one `<AppShell>` owning sidebar + header + `<main>`; real data in the telemetry slots (§2.4); `<Link>` everywhere (§2.2); a nav entry for Settings; the theme toggle in the header cluster beside sign-out (`Layout.tsx:186-193`).

**Breakpoints:** four-tier rather than binary — `<640` stacked · `640–1023` single column + bottom-sheet nav · `1024–1439` persistent sidebar, 2-col · `≥1440` 3-col dashboard. Replace the fixed `w-72`/`md:pl-72` coupling (`Layout.tsx:31,126`) with a size token so the offset can't drift.

---

## 6. Functional dependencies and redesign risks

### 6.1 Transport and realtime [V]

- **WebSocket only** — one socket: `useLiveEmotionStream.ts:143` `new WebSocket(\`${resolveWsBase()}/ws/session/${sessionId}/emotion\`)`, `binaryType="arraybuffer"` `:146`. No `EventSource`, no polling. [V] (grep for both returned nothing else)
- **Audio uplink is an AudioWorklet.** `audioCtx.audioWorklet.addModule(\`${BASE_URL}audio-processor.js\`)` (`:236-238`) → `new AudioWorkletNode(ctx, "pcm-worklet-processor")` (`:247`) → `port.onmessage` → `ws.send` (`:249-253`). The registered name in `public/audio-processor.js:36` must match. [V]
- **No reconnect.** `ws.onclose`/`onerror` (`:164-165`) only set `isConnected=false`. There is no retry, heartbeat or queue. [V]
- **No canvas anywhere.** `getContext`, `<canvas>`, `ResizeObserver`, `devicePixelRatio`, `getBoundingClientRect` — **0 matches** in `src`. Every "visualisation" is inline SVG or recharts. So no chart depends on imperative sizing. [V]
- `isConnected` is returned but consumed by nobody (§1.3) — so the silent-loss case in §6.1 has no user-visible signal today. [V]

### 6.2 Capture / playback inventory [V]

| Capability | Where |
| :-- | :-- |
| `getUserMedia` | `useMediaRecorder.ts:34` (video 1280×720 + audio); `useLiveEmotionStream.ts:211` (audio-only, own stream) |
| `MediaRecorder` | `useMediaRecorder.ts:57-79` (`isTypeSupported` negotiation `:57`, `start(250)` `:79`, `ondataavailable` `:59`, `onstop` `:62`) + 3 per-Studio copies (`HRStudio.tsx:164-174`, `GuesstimateStudio.tsx:235-245`, `TechnicalStudio.tsx:205-219`) |
| `AudioContext`/Worklet | `useLiveEmotionStream.ts:223-255` |
| `SpeechRecognition` | `HRStudio.tsx:115-135`, `GuesstimateStudio.tsx:173-194`, `TechnicalStudio.tsx:168-189` |
| `speechSynthesis` TTS | studios `HR:137-151`, `Guess:208-222`, `Tech:235-249`; reports `HR:32-53`, `Guess:31-52`, `Tech:60-75` |
| `<video>` | `VideoPreview.tsx:24-30`, driven imperatively by `srcObject` (`:11-20`); ref from `RecordingSession.tsx:16,89` |
| `<audio>` | `ProtectedAudioPlayer.tsx:154-160`; `AnalysisResults.tsx:505-554` (10 media events); `TechnicalReport.tsx:493-497` (raw `src`); `SentenceAnalysis.tsx:49` (`new Audio`) |
| `createObjectURL` | `useMediaRecorder.ts:67`, `ProtectedAudioPlayer.tsx:122`, `AnalysisResults.tsx:104`; revoke at `useMediaRecorder.ts:95`, `audioBlob.ts:130` |
| File upload | multipart `sessions.ts:39-49`; resume upload `technical.ts` via hidden input `TechnicalStudio.tsx:623-630` |
| `window.print()` | `AnalysisResults.tsx:409`, `HRReport.tsx:37`, `GuesstimateReport.tsx:36`, `TechnicalReport.tsx:56` |

### 6.3 Auth / ownership boundary [V]

Token travels as an `Authorization: Bearer` header (`client.ts:17-20`) from `localStorage["speakflow_token"]`; 401 clears it (`client.ts:24-32`). Clips are fetched as blobs and played from an object URL precisely *because* a media element cannot send a header (`audioBlob.ts:91-98`, `ProtectedAudioPlayer.tsx:121-131`). `audioBlob.ts:63-87` `toApiPath` is the security seam: it forces the stored `audio_url` onto a root-relative `/api/…` path on a *configured* origin and rejects external hosts, credentials-in-URL, traversal and query/hash — so the bearer token never leaves for a third-party origin.

Two surfaces **bypass** that boundary: `TechnicalReport.tsx:493-497` (`<audio controls src={q.audio_url}>`) and `SentenceAnalysis.tsx:49` (`new Audio(audioUrl)`). [V] Whether these currently work depends on how the backend serves those URLs — **[U]**, and it is N3-adjacent. **The redesign must not "tidy" these into `ProtectedAudioPlayer`** — that is a behaviour change, not a visual one. Consistent with the standing rule that the backend is the authorization boundary and private recordings outrank playback convenience.

**Auth-state desync [V]:** on 401 the interceptor deletes `speakflow_token` from `localStorage`, but `AuthContext`'s `token`/`user` state is untouched, so `isAuthenticated` (`AuthContext.tsx:92`) stays `true` and the chrome keeps showing the user as signed in. The redesign will add a theme toggle next to sign-out; it should not be assumed the session indicator is accurate. Fix is a one-line context reaction — out of scope here, listed as Q7.

### 6.4 Risk table

| Component | Coupling | Why, and what must survive a visual rewrite |
| :-- | :-- | :-- |
| `RecordingSession.tsx` | **HIGH** | `videoRef` (`:16`) identity, passed to `<VideoPreview ref>` (`:89`) and to `useFaceTracking` (`:43-46`). Upload chain `:50-76` + all six `RecordingControls` props (`:115-124`). The parent `relative` wrapper positions the overlay over the video. |
| `VideoPreview.tsx` | **HIGH** | Must stay `forwardRef` with **one persistently mounted `<video>`**. `autoPlay` (`:26`), `playsInline` (`:27`), `muted` (`:28`), `controls` (`:29`), `src` (`:30`) are computed lifecycle inputs — dropping `playsInline`/`muted` breaks iOS autoplay/feedback; converting the wrapper to `{cond && <video>}` kills `srcObject`. |
| `useMediaRecorder.ts` | **HIGH** | `ondataavailable`/`onstop` must keep firing (`:59,:62`) or the blob is empty. Teardown at `:94-97,106-113`. |
| `useLiveEmotionStream.ts` | **HIGH** | Effect deps `[sessionId, isRecording, externalStream]` (`:280`) *define* when mic+socket open. `cleanup()` ordering (`:91-139`) + unmount teardown (`:304-337`). No markup, but consumer prop changes alter capture behaviour. |
| `public/audio-processor.js` | **HIGH** | Not React, not CSS. Worklet name must match `:247`. Loaded by public URL — **do not rename or move.** |
| `ProtectedAudioPlayer.tsx` | **HIGH** | The `<audio>` must stay mounted; `hidden` (`:158`) is a *visibility attribute*, not a mount condition — the file's own comment at `:149-151` states keeping it mounted is what lets `install()`/`release()` work. `el.setAttribute("src", …)` (`:131`) is imperative; React never sets `src`. `className` flows to the node, so sizing is safe but removing `controls`/`hidden` is not. |
| `api/audioBlob.ts` | **HIGH** | Logic, not UI. `toApiPath` guard + generation store + `playbackReleaseSteps` underpin two players. |
| `AnalysisResults.tsx` | **HIGH** | 1,275 lines; 10 media handlers (`:509-553`), `setAttribute("src")`+`load()` (`:106-107`), seek writes `audio.currentTime` (`:192`), `window.print()` (`:409`). Restyle the report; do not restructure the audio sub-block or its `className="hidden"` mounting. |
| 3 × Studio pages | **HIGH** | Each triple-couples `recognitionRef` + `mediaRecorderRef` + `useLiveEmotionStream` on `isRecording`. `toggleRecording` (`HR:153`, `Guess:224`, `Tech:191`) and submit handlers (`HR:221` etc.) must fire unchanged. Timer `setInterval` + `isStarting`/`isSubmitting` guards are behavioural, not cosmetic. `{isRecording && <LiveConfidenceNeedle/>}` (`HR:673`, `Guess:770`, `Tech:863`) gates a socket consumer. Technical's hidden `fileInputRef` input (`:623`, `.click()` `:681`) is DOM-identity-coupled. |
| `RecordingControls.tsx` | **MEDIUM** | No media refs — restyle-safe **only if** the `status`→button conditionals (`:99-123`) survive, because that conditional *is* the double-start guard. Keep the inline `style.width` at `:74`. |
| `TopicSpinner.tsx` | **MEDIUM** | Own `setInterval` spin (`:36`) + `disabled`/`isSpinning` gating (`:61,94,123`) and `onChange` (`:122`) are state, not appearance. |
| `LiveConfidenceNeedle.tsx` | **MEDIUM** | Pure props→SVG, no refs/handlers — but colours come from inline hex (`:28-31,42-43,56`), so a CSS theme swap **will not recolour it**; it needs prop edits. Keep `viewBox`/`strokeDashoffset` geometry consistent. |
| `TechnicalReport.tsx`, `SentenceAnalysis.tsx` | **MEDIUM** | Direct `src`/`new Audio` playback + `setTimeout` auto-stop (`:65`) + refs. Keep elements and play handlers; layout is free. |
| `Layout.tsx` | **LOW** | No media, no timers, one `useState(mobileOpen)`. The shell is the *safest* substantial rewrite — but it is the only place `navItems` exists (`:10-17`), so route labels/paths must be carried over deliberately. |
| `Common/*`, `AuthModal`, all Reports' text sections, Dashboard widgets, `FaceTrackingOverlay`, `LiveCoachNudge`, `VocalDeliveryCard`, `FeedbackSection`, `TranscriptionView`, `MetricsChart` | **LOW** | Props→DOM presentation. Preserve `role="status"`/`"alert"` + `aria-live` on `LiveCoachNudge:13-14`, and `style.height` data bindings in `VocalDeliveryCard:328`. |

### 6.5 Fragile-pattern checklist for the redesign

Anything in this list must be preserved **verbatim** or re-verified by a human, not "cleaned up":

1. Attribute-only visibility on media nodes. `hidden`/`aria-busy` must stay attributes; **never** convert to `{ready && <audio>}`. [V]
2. `muted playsInline autoPlay controls preload` on `<video>`/`<audio>`. [V]
3. Ref identity: `videoRef`, `elRef`, `audioRef`, `speechRef`, `fileInputRef`, `recognitionRef`, `mediaRecorderRef`, `recorderRef`, `chunksRef`, `streamRef`, `ownsStreamRef`, `workletNodeRef`, `sourceNodeRef`, `audioContextRef`, `wsRef`. [V]
4. Effect dependency arrays that gate capture: `useLiveEmotionStream.ts:280`, `:338`; Studio timer deps (`HR:105-111`, `Guess:164-170`, `Tech:159-165`). Note Technical's deps omit `isRestoring`, unlike HR/Guesstimate — an existing asymmetry, not to be "unified" silently. [V]
5. Media event handler sets (`AnalysisResults.tsx:509-553`). [V]
6. State-gated button conditionals (`RecordingControls.tsx:99-123`) and `isStarting`/`isSubmitting` double-action guards. [V]
7. localStorage keys: `speakflow_token`, `speakflow_user`, `speakflow_api_url`, `speakflow_model`, `speakflow_active_{hr,technical,guesstimate}_session`, `verbaliq_preset_{persona,wpm}`. Renaming any breaks resume/auth silently. [V]
8. `audio_url`/`audioUrl` prop names and `toApiPath`'s expectations. [V]
9. The worklet filename and registered processor name. [V]
10. Inline `style={{width|height}}` bound to data on bars/gauges. [V]

### 6.6 The safety net does not exist [V]

There is **no test runner, no Storybook, no E2E**. `package.json:6-11` scripts are `dev`/`build`/`preview`/`lint`, and `lint` is `tsc -b`. No `vitest`/`jest`/`playwright`/`cypress`/`@testing-library` in either dependency block. No `*.test.*`, `*.spec.*` or `*.stories.*` outside `node_modules`.

Therefore `tsc -b` is the **only** automated net, and it catches prop/type drift but **cannot** catch: an unmounted media node, a dropped `playsInline`, `hidden`→conditional-render, or a broken effect-dep lifecycle. **Every one of those is exactly what a visual rewrite tends to break.** [V]

**Hard precondition for the redesign:** agree a written manual verification script (camera+mic permission prompt, live needle moving during recording, upload reaching `/analysis`, authenticated clip playing, resume-after-refresh from each `speakflow_active_*_session`) executed before and after each phase — or add a small behavioural test suite first. Without one, phases 4–5 (§7) are unguarded. I am not claiming any coverage exists; there is none, and I ran nothing.

---

## 7. Recommended redesign sequence

Ordered so that **regression risk rises as confidence in the token layer rises.** Nothing here is implemented.

| Phase | Work | Risk | Gate to pass before proceeding |
| :-- | :-- | :-- | :-- |
| **0 — Decisions** | Resolve Q1–Q3, Q8, Q10 (brand, fabricated telemetry, icon system, a11y target, test net). Agree the freeze list (§6.5). | none | Sign-off |
| **1 — Token layer, additive only** | CSS variables + light values in `:root`, dark under `[data-theme]`; re-point `tailwind.config.js:7-55`; add tone/radius/elevation/typography scales. **Delete no component. Restyle no page.** | **Low** | App must look pixel-identical in dark. Compare before/after screenshots of all 16 routes. |
| **2 — Theme plumbing** | `ThemeProvider`, `speakflow_theme` persistence, `matchMedia` system default, pre-paint script in `index.html`, remove hardcoded `class="dark"`. Toggle placed in a temporary header slot. | **Low** | Toggle works with no flash; survives reload; dark default unchanged. |
| **3 — Primitives** | Build `Badge Tabs Modal ProgressBar FormField EmptyState ErrorNotice PageShell AmbientBackdrop` in `components/Common/`. Rebuild `Button`/`Card`/`Loading` on tokens (this also clears DEF-1/DEF-2 and the invalid utilities). **Do not migrate call sites yet.** | **Low** | Unused-by-app code; review only. |
| **4 — Shell** | Rewrite `Layout.tsx` onto primitives: nav + Settings entry + `<Link>` fixes + theme toggle + real-or-removed telemetry. Delete or revive the two orphaned files. | **Low-Med** | 16 routes still navigable; auth/logout/modal still wired; drawer works on mobile. |
| **5 — Read-only pages** | `SettingsPage` (bring onto tokens — it is currently off-theme), `AuthPage` + `AuthModal`, `HomePage`, Dashboard widgets, then the 3 report pages' **text/layout** sections. | **Med** | Reports: audio playback, TTS and print export still function per page. |
| **6 — Data-heavy widgets** | recharts + SVG theming via the JS token bridge (§5.5 step 7); gauge/needle/band colours; radar and sparkline geometry. | **Med** | Charts legible in both themes; values unchanged; no colour-only meaning added. |
| **7 — Studios** | `HRStudio`, `GuesstimateStudio`, `TechnicalStudio` — last of the non-capture surfaces, sharing `<StudioLayout>`; unify the three `@media print` blocks. | **High** | Full manual capture script per studio × both themes; resume-from-localStorage verified. |
| **8 — Capture surfaces** | `VideoPreview`, `RecordingControls`, `RecordingSession`, `ProtectedAudioPlayer`, `AnalysisResults` audio block, `useLiveEmotionStream` consumers. **Style-only, markup-preserving.** | **Highest** | Manual script on desktop + iOS Safari + Android; mic permission, blob upload, playback, teardown. |
| **9 — Cleanup** | Adopt `@` alias or delete it (§1.3); remove the dead spacing scale or use it; consolidate icons; add code-splitting (§9). | Low | |

**Why this order minimises regression risk.** Phases 1–3 cannot break behaviour: they add variables and unused components. Phase 4 is the largest visible win on the lowest-coupling file (`Layout.tsx` has no media, no timers). Read-only pages precede data visualisation because charts need a token bridge that only exists once variables land. Studios and capture surfaces come last because they are the only places where a cosmetic-looking edit can silently disable the microphone, the upload, or authenticated playback — and §6.6 means a mistake there is invisible to tooling. If time runs out, stopping after phase 6 yields a coherent themed app; stopping after phase 7 would be the first point where a silent functional break is plausible.

---

## 8. Defects catalogue (found incidentally; not fixed)

None of these are visual-only. They are recorded because the redesign will trip over them.

| ID | Severity | Defect | Evidence | Verified? |
| :-- | :-- | :-- | :-- | :-- |
| DEF-1 | **High** | "Stop recording" button renders unstyled — `btn-danger` is emitted as a class but is not defined anywhere. | `Common/Button.tsx:13` ← `RecordingControls.tsx:110`; `index.css` defines only `.btn-primary`(`:43`) `.btn-ghost`(`:49`) | [V] code / [U] pixels |
| DEF-2 | **Med** | Loading spinner has no ring colour; rotation is likely invisible. Used on both primary async routes. | `Common/Loading.tsx:7-8`; `primary-500`/`primary-400` don't exist (`tailwind.config.js:54`) | [V] code / [U] pixels |
| DEF-3 | **Med** | `/settings` unreachable except by typing the URL. | `Layout.tsx:10-17` vs `Sidebar.tsx:8`, `Header.tsx:8` | [V] |
| DEF-4 | **Med** | SPA routes opened via hard `<a href>` → full reload. | `GuesstimateProgressDashboard.tsx:423-429`, `:498` | [V] |
| DEF-5 | **Med** | Auth UI shows signed-in after a 401 clears the token. | `client.ts:24-32` vs `AuthContext.tsx:21,92` | [V] |
| DEF-6 | **Med** | No error boundary + unguarded `JSON.parse` at auth boot → one corrupt localStorage value blanks the app. | `AuthContext.tsx:24`; boundary grep = 0 | [V] code / [U] crash |
| DEF-7 | **Med** | Live telemetry can silently stop with **no** UI signal and no reconnect; `isConnected` is computed but never displayed. | `useLiveEmotionStream.ts:164-165,339` | [V] |
| DEF-8 | **Low** | Print fidelity differs across the three dossiers (A4 + colour-exact only on Guesstimate). | `GuesstimateReport.tsx:102-121` vs `HRReport.tsx:107`, `TechnicalReport.tsx:126` | [V] |
| DEF-9 | **Low** | 5 invalid utility families in live code (`rounded-xs`, `shadow-xs`, `backdrop-blur-xs`, numeric `primary-*`, `btn-danger`). | §5.3, proven by compiling the project's own config | [V] |
| DEF-10 | **Low** | Unclamped inline bar widths can render negative/over-100 % if the API returns out-of-range scores; only 2 of 12 sites clamp. | `TechnicalReport.tsx:247`, `GuesstimateReport.tsx:727` vs the other 10 | [V] code / [I] outcome |
| DEF-11 | **Info** | Socratic `nudge` is returned for every round but surfaced only on Guesstimate. | `GuesstimateStudio.tsx:103,773`; HR/Tech destructure `liveEmotion` only (`HR:60`, `Tech:99`) | [V] |
| DEF-12 | **Info** | Fabricated status telemetry in the shell and HomePage (§2.4) — no backing field exists in frontend types or `backend/app/routes/progress.py`. | [V] |

---

## 9. Additional observations

- **Bundle:** 1.16 MB in one chunk, 67 KB CSS, with **zero** code-splitting (`lazy`/`Suspense`/dynamic `import()` = 0). All 16 routes plus recharts and framer-motion load for a first visit to `/`. [V] A redesign that adds primitives won't fix this; route-level splitting is a separate cheap win — but it is a *build* change, so it must be explicitly authorised, not done "while we're in there".
- **`dist/` is stale** (Nov 1) relative to the current working tree and is gitignored (`frontend/dist/`) — it is not evidence of the current UI. [V]
- **Frontend fonts + Material Symbols load from Google Fonts CDN** (`index.html:9-18`) with no documented offline/self-host strategy. [V] Relevant if the redesigned product is used on campus networks or needs an SLA.
- **`VITE_API_URL` default is `http://localhost:8000`** (`client.ts:3-5`) and `/settings` lets the user overwrite it at runtime (`SettingsPage.tsx:16`), which then redirects *all* traffic including the bearer token — this is exactly why `toApiPath`'s origin allowlist exists (`audioBlob.ts:41-56,63-87`). Any redesign must keep that override visible and deliberate; it is a security-relevant control surface, not a cosmetic field. [V]
- The React `key`-less list risk and the `noUnusedLocals:false` setting (`tsconfig.json:16-17`) mean dead locals will not be flagged; expect to find more orphaned code than this audit surfaced. [I]

---

## 10. Open questions — needs a decision before redesign

| ID | Question | Why it blocks |
| :-- | :-- | :-- |
| **Q1** | Which brand is canonical — **VerbalIQ**, **SpeakFlow**, or neither? Affects browser title, logo, auth CTA, printed dossier, and the split `speakflow_*`/`verbaliq_*` storage keys. | Cannot design the shell or the print dossier; storage-key rename is a breaking change (§6.5-7). |
| **Q2** | Icon system: keep **Material Symbols** (281 sites, zero new deps, themes via `currentColor`) and fold lucide's 9 files into it — or the reverse? | Determines whether icons need per-theme treatment. |
| **Q3** | The fabricated telemetry (§2.4, DEF-12): delete it, or wire it to `ProgressSummary` (which already has `avg_eye_contact`, `avg_posture_quality`), or commission the missing backend fields (streak has **no** source)? | Blocks the shell redesign; one option requires backend work that is currently out of scope. |
| **Q4** | Should `dark:` variants ever be used, or is the whole app strictly token-driven (`data-theme` + CSS vars only)? Mixing both doubles the surface to test. | Phase 1 contract. |
| **Q5** | Is `/settings` the home for the theme toggle, or is a header control plus a Settings entry expected? Currently Settings has no nav route (§2.2). | Phase 4. |
| **Q6** | Should the three Studios share one `<StudioLayout>`, accepting that Technical's timer deps differ today (`Tech:159-165` omits `isRestoring`)? Unifying them is a **behaviour** change. | Phase 7. |
| **Q7** | Fix DEF-5 (post-401 auth desync) and DEF-6 (boot crash) as part of the redesign, or keep them on the backend/auth remediation track? Both are cheap and both touch files the redesign will edit. | Avoids "while we're in there" scope creep. |
| **Q8** | Add a headless a11y primitive library (for real dialog/tab/menu semantics — currently zero exist), or hand-write keyboard support? The only concrete reason for a new dependency in this audit. | Phases 3, 5. |
| **Q9** | Replace `TechnicalReport`'s raw `<audio src>` and `SentenceAnalysis`'s `new Audio` with `ProtectedAudioPlayer` — or leave the two playback paths split? Requires checking the backend's serving contract; a behaviour change, not a visual one. | Phase 5/8; touches the authorization boundary. |
| **Q10** | What is the accessibility target (WCAG 2.1 AA assumed?) — it decides whether 213 sub-11 px text instances, border-only focus indicators on 17 of 22 fields, and colour-only status are acceptable. | Phases 1, 3, 6. |
| **Q11** | Is a test net required *before* phases 7–8, given none exists (§6.6)? | The only thing standing between a visual rewrite and a silent mic/playback regression. |
| **Q12** | Does dark mode need to be per-user server-side (survives devices), or is `localStorage` acceptable? Existing precedent is `localStorage` for everything. | Phase 2. |

---

## 11. Workspace preservation evidence

**Scope of my writes.** Exactly two filesystem operations created anything, both inside the requested report path: `mkdir -p docs/ui` and this file. The three Tailwind probe scripts were written to `C:/Users/Sohail/AppData/Local/Temp/` (outside the workspace) and deleted.

**Baseline captured before any write:** `HEAD = 326d75e…`, `git stash create → d920e0d096b6c9ff68b186c03cd678232f3138b7` (creates an object; does not touch the tree), `git status --porcelain=v1` = 40 lines, `git diff | sha256` = `4a19b2834db0…242c5e`, and per-file sha256 for all 14 in-scope frontend files (11 modified + 3 untracked: `api/audioBlob.ts`, `components/Recording/ProtectedAudioPlayer.tsx`, `public/audio-processor.js`). Full manifest:

```
001f3b76dd7f67756791d46d9498aaf20e4c1ec24036a606b00521a2d7f18dd6  frontend/public/audio-processor.js
4b0acb647d7711424f2e0458ffac18eaca40b4c8f67faab1526d76ea5a4e2499  frontend/src/api/audioBlob.ts
d6deaba37e32044f298563c9acc35fe3b5e45e4628138fd9db417510ff7a759c  frontend/src/components/Analysis/AnalysisResults.tsx
89b74002b54040bfb010525eebdc1c5e8e856f42c1beda91f9dbb5ce078e0aad  frontend/src/components/Dashboard/CurriculumCoachCard.tsx
ed5709a9909ee23199f77f32a3610721055a9389294584947d8fc35bfea32012  frontend/src/components/Interview/LiveConfidenceNeedle.tsx
6926d303fed3133543eeaa7d76be75cacc4ed6e67575927b2a0a79f26efd015d  frontend/src/components/Interview/VocalDeliveryCard.tsx
435e1443219857789de6d742bdddcefe3bc0cf1688b60afc0c7803dff5c18040  frontend/src/components/Recording/ProtectedAudioPlayer.tsx
f4fc9c3f1fb66a81f12a8a1581e17d5fe0543f7416b6510dd2bf79320b4b4530  frontend/src/components/Recording/RecordingSession.tsx
1eb226fb2aa2092ec4f237cee002023fbba0626b331cfcf4b513a5f1a8a49e47  frontend/src/hooks/useLiveEmotionStream.ts
02e44ca0f7bb9433327580da5df65e5ddc7096f95b628d82b1983d2648189448  frontend/src/pages/AnalysisPage.tsx
4cfa18d272f19aba9b3c642bf2f364baeb545dae89760b42ac9605491ce6f4d3  frontend/src/pages/DashboardPage.tsx
68aedbd2db659c7c1a4aa48820091db8acb4f8436e29c56eb1bc9339f32880c5  frontend/src/pages/guesstimate/GuesstimateReport.tsx
d29c675af4a40146d4fddcc90a4ea3a06e3698cca0d1992c32c096f7294f16f4  frontend/src/pages/hr/HRReport.tsx
2a693033a746c32a52242c437800eea729b6a803c64f246ba089a6dd5b632003  frontend/src/types/index.ts
```

**What this proves:** those 14 files are byte-stable across the audit. `git diff | sha256` additionally proves the *combined tracked* modification set is unchanged.

**Untracked-content delta, accounted exactly.** Baseline `git ls-files -o --exclude-standard` = 28 files = 21 non-`docs/` + 7 `docs/audits/*.md`. Final = 29 = **the same 21 non-`docs/`** + 8 under `docs/` (the same 7 `docs/audits/*.md`, none modified, plus `docs/ui/FRONTEND_UI_AUDIT.md`). The single new file is this report, and the delta reconciles without residue. `git status --porcelain=v1` stayed at 40 lines throughout — because `?? docs/` collapses the directory, which is precisely the limitation noted below, and is why the expanded `ls-files` count is the load-bearing check here.

**What it cannot prove (stated plainly):**
- `git status --porcelain` collapses untracked directories — `?? docs/`, `?? frontend/public/`, `?? backend/tests/` are single lines. I therefore also recorded `git ls-files -o --exclude-standard` = 28 files, which enumerates them but **silently omits ignored paths**, so it cannot support "all pre-existing untracked content preserved".
- mtime-based checks were not used and would be unsound: pre-existing files legitimately carry later mtimes, and mtime cannot see an in-place rewrite or a deletion.
- No hash manifest was taken for the ~68 tracked-unchanged frontend files or the backend tree; those rest on `git diff`/`git status` being unchanged, which does cover tracked content but not ignored files.
- Symlink/junction targets, directory metadata, ACLs and timestamps are not covered by any capture above.

**Post-write re-check — executed, results recorded.** After the last edit to this report: `git status --porcelain=v1` = 40 lines and `diff` against the baseline file returned no differences; `git diff | sha256sum` = `4a19b2834db0…242c5e`, identical to baseline; `sha256sum -c` on all 14 manifest entries returned `OK` ×14 with no failures.

### Commands used (all read-only, no server, no build)
`git status` · `git rev-parse` · `git diff --stat` · `git diff | sha256sum` · `git stash create` · `git ls-files` · `git check-ignore` · `ls` · `find` · `wc` · `grep` · `cat` · `sha256sum` · `node -e` requiring the project's own `tailwindcss`/`postcss` with output to `$TEMP` · Read/Edit/Glob/Grep on files under `frontend/` and the two backend/type files quoted above.

**Not run:** `npm install`/`update`/`remove` · `vite`/`vite build`/`tsc -b` (writes `.vite`, `dist`, `.tsbuildinfo`) · any formatter or lint-fix · any migration or codegen · any server or browser. `mkdir` + this file are the only workspace writes.

---

## 12. Summary of conclusions

1. **Architecture** — React 18 + Vite 5 + Tailwind 3.4 + react-router 6, with react-query and a shared `api/` layer present but unevenly adopted: 11 correct query hooks in `hooks/useSessions.ts` are consumed by 3 components while 14 files hand-roll `useState`/`useEffect` fetching. [V]
2. **Routes** — 16 route entries across 12 page components in three structural families (hub / studio / dossier). `/settings` is unreachable; 2 SPA links are hard anchors. [V]
3. **Components** — one genuinely shared primitive (`Card`, 29 uses). `Button` and `Loading` are defined but under-adopted (10 and 4 uses) **and both carry defects**. No badge, tabs, table, form-field, progress-bar, empty-state or error-notice primitive exists; those are re-implemented 12 / 5 / 4 / 3 / 11 times respectively. [V]
4. **Design** — the role-token vocabulary is good and the fonts are well chosen; colour, type, spacing, elevation and density are all inconsistent, and the app ships an abandoned light theme and a third brand name on disk. [V]
5. **Theme** — there is **no** theme system: `class="dark"` is hardcoded, token values are static dark hex, `var()` is used 0 times, `dark:` appears once, and nothing is persisted or follows the OS. Re-pointing tokens to CSS variables is the prerequisite for everything else. Proven against the installed Tailwind's own compiled output. [V]
6. **Risks** — capture/realtime coupling is concentrated in 8 files (`RecordingSession`, `VideoPreview`, `useMediaRecorder`, `useLiveEmotionStream`, `ProtectedAudioPlayer`, `audioBlob`, `AnalysisResults`, the 3 Studios) and the worklet file. There is **no test, no E2E and no error boundary**, so the failure modes a visual rewrite actually causes are invisible to tooling. [V]
7. **Architecture proposed** — light-first token layer (`:root` + `[data-theme="dark"]`), `ThemeProvider` mirroring `AuthProvider`, `speakflow_theme` persistence with a pre-paint script and `matchMedia` fallback, a JS token bridge for charts, 10 new primitives in the existing `Common/` folder, four-tier breakpoints, and 9 phases ordered so risk rises only after the token layer is proven. [proposed]
8. **Defects** — 12 catalogued, of which DEF-1 (unstyled Stop button), DEF-2 (invisible spinner), DEF-7 (silent telemetry loss) and DEF-12 (fabricated status telemetry) are the ones a redesign cannot design around. [V]
9. **Blocked on** — 12 open questions (§10), chiefly brand identity, the fabricated-telemetry decision, the icon system, the a11y target, and whether a test net is required before touching capture surfaces.
10. **No implementation performed.** Audit only; the redesign has not started.
