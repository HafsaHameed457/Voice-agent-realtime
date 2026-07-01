# Voice Agent Realtime

A real-time voice agent with speech-to-text, LLM inference, and text-to-speech, powered by Groq and Edge TTS.

**Live Demo:** [https://voice-agent-realtime-rint.onrender.com](https://voice-agent-realtime-rint.onrender.com)

## Architecture

```
Frontend (Vite + React)          Backend (FastAPI + Uvicorn)
       │                                │
       │  WebSocket (audio stream)      │
       ├───────────────────────────────►│
       │  WebSocket (transcript, audio) │
       │◄───────────────────────────────┤
       │                                ├──► Groq STT (Whisper)
       │                                ├──► Groq LLM (llama)
       │                                └──► Edge TTS
                                      Redis (session state)
                                   Prometheus (metrics)
```

- **Frontend**: Records microphone audio, performs silence detection, sends audio blobs via WebSocket, plays back TTS responses
- **Backend**: Receives audio, transcribes via Groq STT, generates response via Groq LLM, synthesizes speech via Edge TTS, streams audio back

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- A Groq API key
- Redis (optional, for production session management)

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your Groq API key
```

### Frontend

```bash
cd frontend
npm install
```

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Groq API key (required) |
| `GROQ_LLM_MODEL` | `llama-3.3-70b-versatile` | LLM model |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` | STT model |
| `SYSTEM_MESSAGE` | *(concise agent prompt)* | LLM system prompt |
| `TEMPERATURE` | `0.8` | LLM temperature |
| `PORT` | `5050` | Backend port |
| `HOST` | `0.0.0.0` | Backend host |
| `LOG_LEVEL` | `INFO` | Logging level |
| `REDIS_URL` | — | Redis URL (uses in-memory if unset) |
| `STT_TIMEOUT` | `10.0` | STT request timeout (seconds) |
| `LLM_TIMEOUT` | `15.0` | LLM request timeout (seconds) |
| `TTS_TIMEOUT` | `10.0` | TTS request timeout (seconds) |
| `SILENCE_TIMEOUT` | `1.0` | Silence before sending audio (seconds) |
| `MIN_AUDIO_DURATION` | `0.5` | Minimum audio clip duration (seconds) |
| `VAD_THRESHOLD` | `500` | Voice activity detection threshold |

## Running

### Backend

```bash
source .venv/bin/activate
uvicorn src.main:app --reload --port 5050
```

### Frontend (dev mode)

```bash
cd frontend
npm run dev
```

Opens at `http://localhost:5173`. The Vite dev server proxies `/browser-stream` WebSocket connections to the backend at `ws://localhost:5050`.

## How It Works

1. User clicks **Call Agent** — frontend requests mic access, creates WebSocket to backend
2. Audio is captured locally, silence-gated (amplitude threshold), and buffered
3. After 1 second of silence, the accumulated audio blob is sent to the backend
4. Backend accumulates audio, transcribes via Groq STT, generates response via Groq LLM, synthesizes speech via Edge TTS
5. TTS audio is converted to mu-law and streamed back to the frontend
6. Frontend decodes mu-law and plays through an AudioWorklet

## Deployment

### Render (Free Tier)

See [DEPLOY.md](./DEPLOY.md) for step-by-step instructions.

Quick steps:
1. Create a **Web Service** for the backend (Python 3.12, `pip install -r requirements.txt`)
2. Create a **Static Site** for the frontend (`cd frontend && npm ci && npm run build`)
3. Set up free Redis on [Upstash](https://upstash.com) (optional, for session persistence)
4. Add environment variables in Render dashboard

**Resources:**
- Backend: `https://voice-agent-api.onrender.com`
- Frontend: `https://voice-agent-realtime-rint.onrender.com`
- Health: `https://voice-agent-api.onrender.com/health`
- Metrics: `https://voice-agent-api.onrender.com/metrics`

### Docker

```bash
docker-compose up
```

The backend runs on port 5050; the frontend is served as static files via nginx or the backend itself.

## Tech Stack

- **Frontend**: React 19, TypeScript, Vite, Web Audio API (AudioWorklet), Tailwind CSS
- **Backend**: Python 3.12, FastAPI, Uvicorn, Groq SDK, Edge TTS, pydub
- **Infrastructure**: Redis (session management), Prometheus (metrics), Gunicorn
- **Audio**: PCM16, mu-law encoding, AudioWorklet processors
