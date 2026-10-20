# VerbalIQ (SpeakFlow v2.4) — Multimodal AI Communication & Interview Coach

> **Real-Time Multimodal Speech Analytics, Utterance-Aligned Video Tracking, and Executive Adjudication for High-Stakes Campus Recruitment & Speaking Drills.**

VerbalIQ implements a state-of-the-art **two-stage "extract cues → LLM fuses" architecture** (aligned with recent affective multimodal research: [arXiv:2512.20938v1](https://arxiv.org/html/2512.20938v1) and [arXiv:2308.14320](https://ar5iv.labs.arxiv.org/html/2308.14320)). Rather than feeding heavy raw video frames into vision-language models, VerbalIQ extracts discrete speech intervals via Silero VAD, samples video frames strictly during those utterance windows via MediaPipe, and feeds distilled structured evidence into a local Qwen model via Ollama with token-level JSON Schema constraints.

---

## 🏗️ Architecture Overview

```
                                  [ Webcam & Microphone Stream ]
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
     [ Audio Stream (16kHz) ]                                      [ Video Stream (30 FPS) ]
                 │                                                             │
                 ▼                                                             │
      Faster-Whisper + Silero VAD                                              │
    (Tuned for 'uh'/'um' hesitations)                                          │
                 │                                                             │
                 ▼                                                             ▼
      [ Utterance Time Windows ] ──────────────────────────────►  OpenCV Windowed Frame Sampler
        [t_start ───► t_end]                                     (3-5 FPS strictly within speech)
                 │                                                             │
                 │                                                             ▼
                 │                                                MediaPipe FaceMesh + Pose
                 │                                              ├── Gaze (Screen-Offset Cone)
                 │                                              ├── Posture Lean (Scale Proxy)
                 │                                              ├── Head Pose & Brow Dynamics
                 │                                              └── Hand Fidgets vs Gestures
                 │                                                             │
                 └──────────────────────────────┬──────────────────────────────┘
                                                │
                                                ▼
                                 [ Aligned Multimodal Record ]
                                 {
                                   "utterance_id": 1,
                                   "transcript": "...",
                                   "face": { "eye_contact": 0.88, "expr": "confident" },
                                   "gesture": { "posture": "upright", "events": [...] }
                                 }
                                                │
                                                ▼
                                    Ollama Qwen (qwen3.5:4b)
                               (Native GBNF JSON Schema Enforcement)
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
     [ Executive Adjudication Report ]                              [ Auditory Coach Voice ]
     ├── Verbal-Nonverbal Congruence Analysis                       ├── Edge-TTS (ChristopherNeural)
     ├── 6-Axis Competency Radar Vector                             └── Avatar Gesture Sync
     ├── Critical Moment Rewrites (A+ Polish)                           ('empathic_nod', 'open_palm')
     └── Curated 15-Min Actionable Drills
```

---

## ⚡ Key Capabilities

### 1. Audio & Speech Analytics
- **Faster-Whisper with Technical Lexicon Normalizer**: Employs an engineering domain initial prompt and an automated compounding normalizer to ensure technical terms (e.g. `"backend development"`, `"frontend"`, `"microservices"`, `"Kubernetes"`) transcribe accurately without phonetic splitting (e.g. avoiding `"back and development"`).
- **Tuned Silero VAD**: Uses a calibrated threshold (`0.35`) and `250ms` speech padding to guarantee that soft vocal hesitations (`"uh"`, `"um"`, `"hmm"`) are preserved verbatim rather than clipped.
- **Acoustic Pause Detection**: Calculates micro-hesitations and frozen pauses ($\ge 0.5\text{s}$) across speaking turns.
- **Dynamic Cadence Sparkline**: Real-time interval WPM calculations across the session.

### 2. Acoustic Prosody DSP Engine & Dual-Factor Confidence Index
- **Pure Physical Soundwave Analysis**: Uses PyAV and SciPy/NumPy autocorrelation to extract vocal energy (RMS dB) and fundamental pitch frequency ($F_0$ in Hz) directly from raw audio streams with zero GPU overhead (~30ms CPU execution).
- **Decoupled from Camera Gaze**: Eliminates webcam parallax distortion and eye contact noise from confidence scoring, basing poise strictly on vocal acoustic reality.
- **Dual-Factor Confidence Index**:
  $$\text{Confidence Score} = 0.50 \times \text{Acoustic Subscore} + 0.50 \times \text{Fluency \& Pause Subscore}$$
  - **50% Soundwave Pitch & Vocal Energy**:
    - **Vocal Projection**: Average RMS soundwave power in dB.
    - **Pitch Modulation**: Optimal $F_0$ dynamic range (18–42 Hz std) rewarding executive vocal melody over monotone delivery.
    - **Terminal Intonation**: Decisive downward drops ($F_0 \downarrow$) earn authority bonuses, while hesitant "uptalk" question inflections ($F_0 \uparrow$) incur penalties.
  - **50% Behavioral Fluency & Pause Control**:
    - Silence freeze penalties for dead pauses $\ge 2.0\text{s}$ and cumulative pause budgets $> 4.0\text{s}$.
    - Continuity pacing between arguments.

### 3. Utterance-Aligned Computer Vision (MediaPipe)
- **Windowed Frame Extraction**: Processes video frames *only* when the candidate is speaking, cutting CV load by 70% and tying physical gestures directly to spoken clauses.
- **Webcam Parallax Compensation**: Implements an elliptical screen-offset tolerance cone ($\pm 15^\circ$ buffer) so candidates aren't penalized for looking at the screen.
- **Affective & Posture Telemetry**: Tracks eyebrow raise/furrow, head stability, torso lean via face magnification proxy, and hand-to-face touching (nervous fidget indicator) vs open-palm emphasis gestures.

### 4. Local LLM Fusion (Ollama with Native JSON Schema)
- Powered by `qwen3.5:4b` running locally on Ollama.
- Uses **Ollama's native JSON Schema mode** (`format: <schema>`) for token-level grammar logit masking, completely eliminating missing keys or conversational preamble.
- Evaluates:
  - **Verbal-Nonverbal Congruence**: Identifies instances where posture or gestures contradicted spoken technical claims.
  - **6 Core Competencies**: Articulation & Clarity, Structure & STAR Logic, Technical Depth & Precision, Pacing & Strategic Pauses, Confidence & Assertive Tone, and Conciseness (Low Fluff).
  - **Critical Moment Rewrites**: Side-by-side original sentence vs executive-level polished rewrite with letter grades (`C-` to `A+`) and actionable coaching tips.

### 5. Auditory Coach Avatar Voice (Text-to-Speech)
- **Primary Voice**: Microsoft Edge Neural TTS (`en-US-ChristopherNeural`) producing an authoritative executive coach voice.
- **Instant Fallback**: Browser-native Web Speech API if offline.
- **Avatar Gesture Synchronization**: Schedules nonverbal reactions (`empathic_nod`, `attentive_tilt`, `open_palm_welcome`) aligned with spoken feedback.

### 6. VerbalIQ Dark Cockpit UI
- High-contrast cockpit theme built on `#10131a` surface baseline with custom tokens (`Plus Jakarta Sans`, `JetBrains Mono`, `Inter`).
- **4 Track Practice Arena**:
  - Track 01: Technical System Design
  - Track 02: HR & Behavioral (STAR Method)
  - Track 03: Guesstimates & Market Sizing
  - Track 04: JAM Blitz (Just A Minute)
- Interactive SVG Radar chart, filler timeline with time chips, and utterance-aligned nonverbal telemetry cards.
- **Acoustic Impression Card**: Live telemetry displaying vocal energy in dB RMS, decisive drop vs. uptalk counts, pitch modulation score, and the dual 50-50 subscores breakdown.

---

## 🚀 Quickstart Guide

### Prerequisites
- Python 3.10+ (tested on Python 3.12)
- Node.js 18+ & npm
- [Ollama](https://ollama.com) installed and running

### 1. Launch Ollama Model
Ensure Ollama is running, then verify or pull the model:
```bash
ollama run qwen3.5:4b
```

### 2. Backend Setup
```bash
cd speakflow/backend

# Activate virtual environment
# Windows:
.\speakvenv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install edge-tts

# Run FastAPI backend
python -m uvicorn main:app --reload --port 8000
```
Backend API will be live at `http://localhost:8000` (docs at `http://localhost:8000/docs`).

### 3. Frontend Setup
```bash
cd speakflow/frontend

# Install packages
npm install

# Start Vite dev server
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 📡 API Endpoints Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/sessions` | Multipart video/audio upload with track type & topic |
| `POST` | `/api/sessions/{id}/analyze` | Triggers Whisper + MediaPipe + Ollama adjudication pipeline |
| `GET` | `/api/sessions/{id}` | Complete session report, metrics, and multimodal timeline |
| `GET` | `/api/sessions/{id}/tts` | Synthesized MP3 audio stream of the coach's feedback |
| `GET` | `/api/progress/summary` | Global progress, practice streak, and competency averages |
| `GET` | `/api/progress/metrics` | Longitudinal performance time-series across practice sessions |

---

## 📄 License
MIT. Built for Campus Recruitment & Executive Speaking Preparation.
