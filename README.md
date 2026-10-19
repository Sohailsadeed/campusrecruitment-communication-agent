# SpeakFlow

AI-powered public speaking coach with real-time feedback. SpeakFlow records
your practice sessions in the browser, transcribes them, measures your
speaking pace, filler words, on-camera presence, and asks a local LLM to
turn all of that into encouraging, actionable coaching.

## Stack

- **Frontend**: React 18 + TypeScript, Vite, Tailwind CSS, TanStack Query v5,
  Recharts, Framer Motion, Axios
- **Backend**: FastAPI, SQLAlchemy 2.0, SQLite, Pydantic v2,
  OpenAI Whisper (optional), MediaPipe (optional)
- **AI**: Local LLM served by [Ollama](https://ollama.com) (defaults to
  `qwen3.5:4b`)

## Project layout

```
speakflow/
├── backend/        FastAPI app, services, and SQLite database
├── frontend/       Vite + React client
├── docker-compose.yml
└── README.md
```

## Running the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The API will listen on `http://localhost:8000`. SQLite data is stored in
`backend/speakflow.db` and uploads in `backend/uploads/`.

> Whisper and MediaPipe are optional. If they aren't installed, SpeakFlow
> falls back to deterministic mock transcripts and presence metrics so the
> app remains fully functional for demos.

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The client reads `VITE_API_URL` (defaults to
`http://localhost:8000`) so you can point it at a remote backend if you
prefer.

## Running with Docker Compose

```bash
docker compose up --build
```

This brings up the FastAPI backend, the Vite dev server, and an Ollama
instance. After it boots, pull a model:

```bash
docker compose exec ollama ollama pull llama3.2
```

## API highlights

- `POST /api/sessions` multipart upload (video/audio + metadata)
- `POST /api/sessions/{id}/analyze` runs transcription + metrics + LLM feedback
- `GET  /api/sessions/{id}` full session detail
- `GET  /api/progress/summary` dashboard aggregates
- `GET  /api/progress/metrics` per-session metric time series

## Environment variables

Create `backend/.env` to override defaults:

```
DATABASE_URL=sqlite:///./speakflow.db
SECRET_KEY=change-me-to-something-random
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
WHISPER_MODEL_NAME=base
```

## License

MIT.
