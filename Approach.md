# Unified Implementation Approach: HR Interview & JAM Practice Modules

## 1. Introduction to the Modules

The communication practice platform consists of two distinct but technically synergistic modules: **HR Interview Practice** and **JAM (Just a Minute)**. Both modules share a foundational philosophy: predictable behavior, explainable evidence-based feedback, and strict backend control over LLM behavior.

### HR Interview Practice Module
This module prepares students for campus-placement HR rounds through controlled mock interviews. 
* **Core Function:** It asks predefined HR questions and allows for a limited, adaptive follow-up if an answer is incomplete.
* **Evaluation Focus:** Content quality, situational awareness, and completeness against a predefined rubric (e.g., Situation, Action, Result, Learning).
* **Key Constraint:** The LLM is heavily bounded. It cannot invent rubrics, ask off-script main questions, or ask more than one follow-up per question.

### JAM (Just a Minute) Module
This module helps students practice speaking clearly, concisely, and relevantly for up to 60 seconds on a given topic.
* **Core Function:** Evaluates both the *delivery* of the speech (pauses, pacing, fillers) and the *content* (relevance, structure).
* **Evaluation Focus:** A dual-layer approach measuring objective audio metrics (WPM, filler words, pause duration) and subjective content quality (topic relevance, clarity, conclusion).
* **Key Constraint:** Objective delivery metrics are calculated purely programmatically (via Python/WhisperX/VAD); the LLM is restricted strictly to analyzing the verified text transcript for content structure.

---

## 2. Unified High-Level Architecture

Both modules utilize a shared three-layer pipeline architecture. Instead of deploying autonomous AI agents, the system relies on a strict separation of concerns where Java acts as the absolute source of truth.

**Architecture Flow:**
1. **React Frontend:** User Interface, session management, audio recording, and feedback display.
2. **Java Spring Boot (Layer 3 - Orchestrator):** State management, authentication, validation, LLM coordination, and database persistence.
3. **Python Speech Service (Layer 1 - Objective Metrics):** FastAPI service running WhisperX and Voice Activity Detection (VAD) for transcription, timestamps, and objective speech metrics.
4. **LLM Evaluator via Spring AI (Layer 2 - Content Analysis):** Processes verified transcripts against rubrics to generate structured feedback, evidence, and (for HR) follow-up questions.
5. **PostgreSQL:** Permanent storage for rubrics, questions, session history, and evaluations.

---

## 3. Component Responsibilities

### Layer 1: Python Audio & Metrics Service (Crucial for JAM, Optional for HR)
* Validates and decodes incoming audio.
* Runs **WhisperX** for highly accurate transcription and word-level timestamps.
* Runs **Voice Activity Detection (VAD)** to accurately distinguish pauses from background noise.
* Calculates deterministic metrics (Recording duration, VAD speech duration, WPM, filler word counts, pause counts, longest pause, immediate repetition).
* *Rule:* Never uses LLMs for metric calculations. Preserves transcription uncertainty instead of silently correcting it.

### Layer 2: LLM Evaluator
* **For HR:** Classifies rubric criteria (PRESENT, PARTIAL, MISSING), extracts transcript evidence, and recommends FOLLOW_UP or CONTINUE.
* **For JAM:** Evaluates topic relevance, structure/flow, clarity, and opening/conclusion on a 1-5 scale.
* *Rule:* Must cite specific evidence from the transcript. Cannot invent quotes, assume intent, or evaluate vocal tone/confidence from text.

### Layer 3: Java Spring Boot Backend
* Authenticates users and owns all session state.
* Selects questions/topics and retrieves rubrics from PostgreSQL.
* Coordinates calls to the Python service and Spring AI.
* Enforces hard limits (e.g., 60-second JAM limit, maximum 1 HR follow-up).
* Validates structured model responses (JSON contracts) before saving them.
* Generates the final API response and feedback dashboard data for the frontend.

---

## 4. Implementation Workflows

### A. HR Interview Workflow
1. **Initialization:** Frontend calls `/api/hr/interviews`. Java creates a session, selects a predefined question, and loads its rubric.
2. **Submission:** Student submits text or audio. If audio, Java routes it to Python for transcription.
3. **Interviewer Assessment:** Java sends the rubric, main question, and transcript to the LLM. 
4. **Follow-up Logic:** The LLM returns a structured assessment. If an essential criterion is missing, Java allows *one* follow-up question. If criteria are met, Java proceeds to the next main question.
5. **Completion:** Once all main questions are answered, a post-interview LLM evaluation generates criterion-level results (Strengths, Improvements, Evidence). Java validates and stores the final assessment.

### B. JAM Module Workflow
1. **Initialization:** Student selects a JAM topic and records audio for up to 60 seconds.
2. **Objective Analysis (Python):** Java sends the audio to Python. Python returns a strict JSON payload containing the transcript, WPM, filler count, VAD-detected pauses, and repetitions.
3. **Subjective Analysis (LLM):** Java sends the transcript and topic to the LLM. The LLM returns a JSON payload scoring relevance, structure, and clarity, backed by transcript quotes.
4. **Validation & Consolidation (Java):** Java verifies that the LLM's evidence actually exists in the Python transcript. It consolidates the Python delivery metrics and LLM content scores into a single feedback payload.
5. **Completion:** The UI displays delivery metrics, rubric scores, strengths, and one concrete next practice goal.

---

## 5. Data Contracts and Database Schema

### Cross-Module Database Tables (PostgreSQL)
| Table | Purpose |
| :--- | :--- |
| `practice_sessions` | Common metadata: user ID, module type (HR or JAM), status, timestamps. |
| `hr_questions` / `jam_topics` | Predefined HR questions (and categories) or JAM topics. |
| `rubric_criteria` | Criteria and essentiality flags associated with questions/topics. |
| `responses` | Student answers, generated follow-ups, audio reference keys, response order. |
| `evaluations` | Evaluation metadata, summary, model/prompt versions. |
| `evaluation_results` | Granular criterion status (1-5 score for JAM, PRESENT/MISSING for HR), text evidence, and feedback. |
| `delivery_metrics` | (JAM Specific) Stored JSON blob or columns for WPM, pause counts, filler words, speech duration. |

### JAM Python-to-Java Data Contract
```json
{
  "response_id": "resp_881",
  "transcript": "...",
  "recording_duration_seconds": 60.0,
  "speech_duration_seconds": 48.0,
  "word_count": 105,
  "words_per_minute": 131.25,
  "filler_count": 6,
  "pause_count": 5,
  "longest_pause_seconds": 2.1,
  "transcript_confidence": 0.91
}
```

### LLM-to-Java Evaluation Contract (Example: HR)
```json
{
  "criteria": [
    {
      "criterion": "Personal actions",
      "status": "PRESENT",
      "evidence": "I listened to both teammates and suggested comparing the options.",
      "explanation": "The student describes their own contribution."
    }
  ],
  "decision": "FOLLOW_UP",
  "followUpQuestion": "What did this experience teach you about resolving disagreements?"
}
```
*Note: Java must rigorously validate this schema, ensuring `status` matches allowed enums, `decision` does not violate max follow-up counts, and `evidence` is a genuine substring of the transcript.*

---

## 6. Guardrails and Quality Assurance

* **Strict Boundary Enforcement:** Java dictates session flow. If an LLM recommends a second follow-up for an HR question, Java blocks it. If a student talks for 90 seconds in JAM, Java truncates or flags the submission based on the 60-second rule.
* **No AI Hallucinations in Evidence:** Java conducts a substring validation to ensure any quote the LLM provides in its feedback perfectly matches the Python transcript. If it fails, the evaluation is flagged for retry or human review.
* **Prompt Injection Protection:** Student inputs are strictly treated as data payloads, not executable instructions.
* **Testing Strategy:**
    * **Audio Tests:** Corrupt audio, transcription failures, heavy background noise (testing VAD accuracy).
    * **LLM Contract Tests:** Missing fields, invalid status values, hallucinated quotes.
    * **Behavior Tests:** Short-but-complete answers, rambling off-topic answers (JAM), essential criteria missing (HR).
    * **Human-in-the-Loop:** Compare LLM scores with human-reviewed sample answers before relying on automated scoring.

---

## 7. Phased Implementation Plan

### Phase 1: Core Framework & Text Workflows
* Set up the PostgreSQL schema (`sessions`, `questions`, `rubrics`, `evaluations`).
* Implement Java Spring Boot session management and Spring AI integration.
* Build the HR text-based workflow (Start -> Type Answer -> Assess -> Follow-up -> Evaluate).
* Enforce backend limits and validate JSON data contracts.

### Phase 2: Python Audio Service & JAM Foundation
* Deploy the Python FastAPI service with WhisperX and VAD.
* Implement the audio ingestion pipeline in Java and React.
* Build the objective metrics engine for JAM (WPM, pauses, fillers).
* Integrate the LLM subjective evaluator for JAM transcripts.

### Phase 3: Unified Dashboards & Refinement
* Develop the React frontend evaluation dashboards (metrics, rubric scores, strengths, transcript highlights).
* Implement audio storage strategy (store audio in object storage, keep keys in Postgres).
* Conduct human-in-the-loop review of evaluations to tune prompts and rubrics.
* Expand the HR question bank and JAM topic library.