# Unified Implementation Approach: SpeakFlow 4-Round Campus Recruitment Preparation Platform

## 1. Introduction to the Modules

SpeakFlow is a specialized, end-to-end communication and interview practice platform designed to prepare candidates for competitive campus placement drives. The platform structures preparation into **four specialized evaluation rounds**, adhering to a core architectural philosophy: **predictable state machines, objective deterministic measurements before subjective evaluation, explainable evidence-based scoring, and zero artificial metric-blurring across rounds**.

### Round 1: JAM (Just A Minute) Fluency Module
This module trains students to speak concisely, coherently, and confidently under a strict 60-second time constraint.
* **Core Function:** Evaluates speech delivery (WPM, pacing zones, filler words, pause duration, silence) and content flow (topic relevance, opening hooks, conclusion).
* **Multi-Modal Sensing:** Integrates audio ingestion with optional computer vision (MediaPipe / OpenCV) for eye contact tracking and head posture stability.
* **Key Constraint:** Objective delivery metrics are calculated deterministically (via Whisper/WhisperX and Voice Activity Detection); LLMs are strictly bounded to analyzing verified transcript text for topical structure.

### Round 2: Technical Interview Module
This module evaluates role-specific engineering articulation across disciplines (Backend, Frontend, Fullstack, Machine Learning, DevOps, Systems).
* **Core Function:** Tests candidates on system design, architecture trade-offs, algorithmic reasoning, and production debugging.
* **Evaluation Focus:**
  * **Conciseness & Anti-Rambling Penalty:** Detects when candidates talk in circles instead of concluding.
  * **Jargon vs. Intuitive Understanding:** Differentiates textbook memorization from practical conceptual grasp.
  * **STAR Technical Execution:** Evaluates technical reasoning, implementation trade-offs, and measurable engineering outcomes.
* **Key Constraint:** Provides sentence-level breakdown identifying optimal conclusion points and flagging ungrounded buzzwords.

### Round 3: Guesstimate & Market Sizing Module
This module prepares candidates for analytical consulting and product management estimation rounds.
* **Core Function:** Presents market sizing, volume estimation, and operational capacity problems across multiple difficulty tiers.
* **Evaluation Focus:**
  * **MECE Decomposition:** Ensures candidate breakdowns are Mutually Exclusive and Collectively Exhaustive.
  * **Math Sanity Engine:** Programmatically validates arithmetic calculations against candidate-declared assumptions.
  * **Proxy & Benchmark Rigor:** Validates whether assumptions fall within realistic industry reference ranges.
* **Key Constraint:** The calculation engine evaluates computational consistency separately from structural decomposition quality.

### Round 4: HR & Behavioral Interview Module
This module prepares students for behavioral competency and cultural alignment rounds.
* **Core Function:** Multi-turn adaptive mock interview drawing from a 40-question database bank across 8 behavioral competencies (`Adaptability`, `Conflict Resolution`, `Leadership`, `Team Collaboration`, `Culture Fit`, `Motivation`, `Career Goals`, `Work Style`).
* **Evaluation Focus:**
  * **STAR Method Coaching:** Tracks coverage across Situation, Task, Action, and Result.
  * **Personal Ownership ("I" vs. "We" Ratio):** Detects whether candidates articulate personal agency or hide behind team actions.
  * **Concrete Specificity & Measurable Outcomes:** Penalizes vague generalizations; rewards quantified business impact.
* **Key Constraint:** State machine limits adaptive follow-ups to at most one per main question when essential STAR criteria are missing. Illustrative scripts are labeled as examples, not absolute ideal answers.

---

## 2. Unified High-Level Architecture

SpeakFlow employs a decoupled, multi-tiered pipeline architecture where the backend acts as the deterministic source of truth, coordinating specialized ML models, audio processors, and LLM evaluators.

```
+-----------------------------------------------------------------------------------------+
|                                    REACT FRONTEND                                       |
|  - 3-Layer Placement Dashboard  - JAM Studio & Report   - Technical Studio & Report     |
|  - Guesstimate Studio & Report - HR Studio & Report    - Audio/Video Web APIs          |
+--------------------------------------------+--------------------------------------------+
                                             | HTTP / REST / Multipart
                                             v
+-----------------------------------------------------------------------------------------+
|                                   FASTAPI BACKEND                                       |
|  - Auth & Session State Machine (/api/sessions, /api/auth)                              |
|  - Round 1: JAM Audio Analysis (/api/analysis)                                          |
|  - Round 2: Technical Evaluation (/api/technical)                                       |
|  - Round 3: Guesstimate MECE Engine (/api/guesstimate)                                  |
|  - Round 4: HR State Machine & STAR Coach (/api/hr)                                     |
|  - Cross-Round Progress & Placement Readiness (/api/progress)                           |
+--------------------+-----------------------+---------------------+----------------------+
                     |                       |                     |
                     v                       v                     v
          +--------------------+  +--------------------+  +--------------------+
          | DETERMINISTIC ML   |  |   LLM EVALUATOR    |  |  PERSISTENCE &     |
          | & AUDIO ENGINE     |  |   (OPENAI/GEMINI)  |  |  LOGGING           |
          | - WhisperX / Whisper|  | - STAR Classifier  |  | - PostgreSQL /     |
          | - Silero VAD       |  | - MECE Evaluator   |  |   SQLite Fallback  |
          | - OpenCV Eye Track |  | - Anti-Rambling    |  | - RotatingFile-    |
          | - Math Sanity Math |  | - Feedback Scripts |  |   Handlers (.log)  |
          +--------------------+  +--------------------+  +--------------------+
```

### Architecture Flow:
1. **React 18 + TypeScript + Vite Frontend:** Modern UI with Tailwind CSS, Lucide icons, Recharts visualizations, synchronized waveform playback, and responsive video recording studios.
2. **FastAPI Backend (Layer 3 - Orchestrator):** Manages user sessions, interview state transitions, question bank querying, input validation, and LLM orchestration.
3. **Deterministic Objective Services (Layer 1):**
   * WhisperX / Whisper for word-level timestamped transcription and confidence scoring.
   * Silero VAD (Voice Activity Detection) for pause, speech duration, and silence boundary calculation.
   * OpenCV / MediaPipe for gaze vector and posture orientation tracking.
   * Symbolic Math Engine for guesstimate arithmetic verification.
4. **LLM Evaluator (Layer 2):** Bounded LLM inference running on structured JSON schemas, analyzing transcripts against strict rubrics and producing verifiable quotes.
5. **Database & Logging Layer:**
   * PostgreSQL (primary) with resilient SQLite dynamic fallback (`speakflow.db`) via SQLAlchemy.
   * Disk-persisted logging via Python `RotatingFileHandler` writing to `backend/logs/speakflow.log` and `error.log`.

---

## 3. Component Responsibilities

### Layer 1: Objective Telemetry & Audio/Vision Engine
* **Audio Processing:** Validates MIME types, normalizes audio to 16kHz mono WAV, and computes audio duration.
* **Transcription & Alignment:** Runs WhisperX to obtain word-level alignment, confidence intervals, and transcript text.
* **Delivery Metrics:** Computes Words Per Minute (WPM), speech-to-pause ratio, filler word occurrences (`um`, `uh`, `like`, `you know`), silence distribution, and repetition counts without LLM guesswork.
* **Visual Telemetry:** Computes face landmark alignment, eye contact percentage, and fidgeting/head drift metrics.
* **Calculation Verification:** Evaluates step-by-step mathematical consistency for guesstimate estimation trees.

### Layer 2: LLM Reasoning & Evaluator Engine
* **JAM Content Scorer:** Assesses topical relevance, structural progression, and clarity on calibrated rubrics with transcript citations.
* **Technical Architecture Evaluator:** Analyzes architectural rigor, flags rote jargon vs. applied comprehension, penalizes rambling, and pinpoints where an answer should have concluded.
* **Guesstimate MECE Engine:** Evaluates framework completeness, step-by-step logical branching, and proxy assumption realism.
* **HR STAR Coach:** Maps transcript fragments to Situation, Task, Action, and Result; calculates personal ownership ratio ("I" vs. "We"); detects concrete metrics and business impact.
* *Rule:* LLMs are never permitted to generate synthetic delivery metrics or quote nonexistent statements. All quotes must be exact transcript substrings.

### Layer 3: FastAPI Backend & State Management
* **State Machines:** Enforces round flow constraints (e.g., 60-second JAM hard limit, 1 adaptive follow-up maximum for HR).
* **Question Bank Service:** Dynamically queries `hr_questions` and guesstimate catalogs from the database with category, role, and difficulty filtering.
* **Calibration & Thresholds:** Presents performance thresholds as calibrated preparation targets (70% Baseline / 85% Target Ready) rather than misleading absolute hiring predictions.
* **Persistence & Auditability:** Commits all evaluations to PostgreSQL/SQLite and writes execution logs to disk.

### Layer 4: 3-Layer Unified Placement Readiness Dashboard
* **Layer 1: Placement Readiness Matrix:** Displays 4 dedicated round cards. Each card surfaces its own primary metric (JAM Delivery, Tech Architecture Rigor, Guesstimate MECE, HR Behavioral Fit) and specialized secondary indicators without cross-round score blurring.
* **Layer 2: Longitudinal Skill Trajectories:** Historical trendlines tracking session-by-session improvement across distinct dimensions against calibrated benchmark bands.
* **Layer 3: Cross-Round Session History:** Centralized session log with round badges, scores, timestamps, and direct deep-links to comprehensive round dossiers (`/analysis/{id}`, `/technical/report/{id}`, `/guesstimate/report/{id}`, `/hr/report/{id}`).

---

## 4. Implementation Workflows

### A. Round 1: JAM (Just A Minute) Fluency Workflow
1. **Topic Selection:** User selects or randomizes a JAM topic and initiates recording.
2. **Audio/Video Capture:** Frontend captures up to 60 seconds of WebM/WAV audio and video frames.
3. **Deterministic Telemetry:** Audio is submitted to `/api/analysis/record`. Whisper extracts words with timestamps; VAD extracts speech vs. silence segments; OpenCV tracks gaze vectors.
4. **Content Evaluation:** Transcript is analyzed for relevance, opening hook, and conclusion structure.
5. **Dossier Generation:** `/analysis/{id}` visualizes the synchronized audio timeline, pacing zones (Optimal 130–160 WPM), filler word timestamps, and eye-contact heatmaps.

### B. Round 2: Technical Interview Workflow
1. **Track Configuration:** User selects technical domain (e.g., Backend, Frontend, ML) and target seniority tier (Junior, Mid, Senior, Lead).
2. **Problem Ingestion:** System provides technical prompt or architectural scenario. Candidate speaks or types response.
3. **Anti-Rambling & Conciseness Audit:** Backend identifies core architectural answer and flags circular restatements or bloated filler phrasing.
4. **Jargon vs. Intuition Verification:** Evaluator separates properly explained technical concepts from memorized buzzwords.
5. **Technical Dossier:** `/technical/report/{id}` renders architecture score, conciseness rating, sentence-by-sentence rambling analysis, and optimized rewrite examples.

### C. Round 3: Guesstimate & Market Sizing Workflow
1. **Case Selection:** User selects category (Market Sizing, Revenue Estimation, Volume Sizing) and difficulty tier.
2. **Tree Decomposition:** User structures estimation into top-down or bottom-up branches.
3. **Math Sanity Check:** Backend symbolically verifies calculations against candidate's declared population, penetration, and replacement rates.
4. **Benchmark Comparison:** Results are evaluated against market bounds (e.g., $80M–$120M target range).
5. **Guesstimate Dossier:** `/guesstimate/report/{id}` displays MECE tree visualization, mathematical correctness score, and sensitivity analysis.

### D. Round 4: HR & Behavioral Interview Workflow
1. **Interview Initialization:** Frontend calls `/api/hr/start` with candidate's target role and company. System loads balanced questions from `hr_questions` table.
2. **Candidate Response:** Candidate records or submits their behavioral answer.
3. **STAR & Ownership Evaluation:** System extracts Situation, Task, Action, and Result components, computes "I" agency percentage, and checks for quantified metrics.
4. **Adaptive Follow-Up State Machine:** If a critical STAR quadrant is absent (e.g., missing measurable Result), the system generates exactly one targeted follow-up. If complete, it moves to the next competency question.
5. **Behavioral Dossier:** `/hr/report/{id}` renders STAR quadrant breakdown, personal agency score, green/red flag feedback, and an illustrative star response script.

### E. Unified 3-Layer Dashboard Workflow
1. **Telemetry Aggregation:** Frontend calls `/api/progress/placement-readiness`.
2. **Matrix Assembly:** Computes readiness status across all 4 rounds based on latest completed attempts.
3. **Trendline Population:** Loads historical timeline points from `/api/progress/jam`, `/api/progress/technical`, `/api/progress/guesstimate`, and `/api/progress/hr`.
4. **History Federation:** Combines all round sessions into chronological table with status badges and dossier routing.

---

## 5. Data Contracts and Database Schema

### Database Schema (SQLAlchemy Models)
* **`users`:** User authentication, credentials, email, timestamps.
* **`sessions`:** Base practice sessions linking user ID, module type, audio file paths, status, timestamps.
* **`transcriptions`:** Raw text, Whisper confidence, word-level JSON timestamps.
* **`session_analyses`:** JAM-specific delivery metrics (WPM, fillers, pause counts, clarity score, gaze score).
* **`technical_sessions`:** Role, seniority, architecture scores, conciseness, rambling rate, jargon penalty.
* **`guesstimate_cases`:** Category, target estimation, MECE tree JSON, mathematical sanity flags, final estimate.
* **`hr_interviews`:** Target company, target role, conversation state machine JSON, overall STAR score, ownership score.
* **`hr_questions`:** 40 canonical questions across 8 categories, target competency, green flags, red flags, sample follow-ups.

### Placement Readiness Contract (`/api/progress/placement-readiness`)
```json
{
  "total_rounds": 4,
  "attempted_rounds": 4,
  "target_ready_rounds": 4,
  "evaluation_rule": "Round metrics are evaluated on distinct specialized rubrics without artificial single-score blurring.",
  "rounds": [
    {
      "round_id": "jam",
      "name": "JAM Fluency (Just A Minute)",
      "status": "ready",
      "attempts": 3,
      "primary_metric": { "name": "Clarity & Delivery", "value": 84.5, "unit": "/100" },
      "secondary_metrics": [
        { "name": "Speaking Pace", "value": "142.0 WPM" },
        { "name": "Filler Words", "value": "3 detected" },
        { "name": "Eye Contact", "value": "88.0% adherence" }
      ],
      "drill_path": "/record",
      "dossier_path": "/analysis/19"
    },
    {
      "round_id": "technical",
      "name": "Technical Interview",
      "status": "ready",
      "attempts": 5,
      "primary_metric": { "name": "Architecture Rigor", "value": 88.0, "unit": "/100" },
      "secondary_metrics": [
        { "name": "Role Focus", "value": "Senior Backend Architect profile" },
        { "name": "Rambling Rate", "value": "0.0% clean conclusion" }
      ],
      "drill_path": "/technical",
      "dossier_path": "/technical/report/20"
    },
    {
      "round_id": "guesstimate",
      "name": "Guesstimate & Market Sizing",
      "status": "ready",
      "attempts": 2,
      "primary_metric": { "name": "MECE Framework", "value": 85.0, "unit": "/100" },
      "secondary_metrics": [
        { "name": "Decomposition", "value": "90% MECE" },
        { "name": "Math Sanity", "value": "85% accuracy" }
      ],
      "drill_path": "/guesstimate",
      "dossier_path": "/guesstimate/report/21"
    },
    {
      "round_id": "hr",
      "name": "HR & Behavioral Interview",
      "status": "ready",
      "attempts": 4,
      "primary_metric": { "name": "Behavioral Fit", "value": 91.0, "unit": "/100" },
      "secondary_metrics": [
        { "name": "STAR Completeness", "value": "95.0% coverage" },
        { "name": "Personal Agency", "value": "88.0% 'I' ownership" }
      ],
      "drill_path": "/hr",
      "dossier_path": "/hr/report/22"
    }
  ]
}
```

---

## 6. Guardrails, Calibrations, and Quality Assurance

* **Zero Single-Score Blurring:** Avoids compressing fundamentally distinct abilities (e.g., vocal delivery vs. distributed systems design) into an ungrounded general score.
* **Deterministic Metrics Grounding:** Audio pacing, fillers, and silence are measured directly from waveform/VAD arrays. LLMs are prohibited from inventing delivery stats.
* **Calibrated Benchmark Lines:** Progression timelines display **Target (85%)** and **Baseline (70%)** reference lines representing calibrated preparation benchmarks, explicitly framed as guidance rather than external corporate hiring decisions.
* **Anti-Hallucination Substring Verification:** Every critique, green flag, or red flag must quote an exact substring from the user's transcript.
* **Illustrative Script Clarification:** Rewritten answers or STAR responses are explicitly labeled as *"Illustrative Example"* rather than singular "Ideal Answers".
* **Persistent Disk Logging:** All server execution runs, error logs, and acceptance suite verifications are stored in `backend/logs/` with automatic size-based rotation (`speakflow.log`, `error.log`, `acceptance_suite.log`).

---

## 7. Phased Implementation Plan & Current Status

| Phase | Description | Deliverables | Status |
| :--- | :--- | :--- | :--- |
| **Phase 1** | JAM Fluency & Speech Analysis | Whisper transcription, VAD silence detection, OpenCV gaze tracking, 60s studio, timeline analysis dossier. | **100% Completed** |
| **Phase 2** | Technical Interview Studio | Role-based tracks, conciseness scorer, anti-rambling penalty, jargon detector, sentence-level analysis report. | **100% Completed** |
| **Phase 3** | Guesstimate & Market Sizing | MECE decomposition tree, symbolic math engine, proxy range validator, guesstimate studio and report. | **100% Completed** |
| **Phase 4** | HR & Behavioral Module | 40-question database seed (`hr_questions`), STAR quadrant analyzer, "I" ownership evaluator, adaptive follow-up state machine, studio & dossier. | **100% Completed** |
| **Phase 5** | 3-Layer Placement Dashboard | Layer 1 Readiness Matrix, Layer 2 Longitudinal Trajectories with benchmark thresholds, Layer 3 unified attempt history, persistent logging. | **100% Completed** |
| **Phase 6** | E2E Acceptance & Production Polish | End-to-end multi-round validation test suite (`100% PASSED`), rotation logging handlers, clean Vite production build. | **100% Completed** |