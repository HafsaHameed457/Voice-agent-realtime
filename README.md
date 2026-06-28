# Voice Agent Realtime

A real-time voice agent with speech-to-text, LLM inference, and text-to-speech, powered by Groq and Edge TTS.

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
```

- **Frontend**: Records microphone audio, performs silence detection, sends audio blobs via WebSocket, plays back TTS responses
- **Backend**: Receives audio, transcribes via Groq STT, generates response via Groq LLM, synthesizes speech via Edge TTS, streams audio back

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- A Groq API key

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

### Production Build

```bash
# Build frontend
cd frontend
npm run build
# Output goes to frontend/dist/

# Serve backend with production ASGI server
pip install gunicorn
gunicorn src.main:app --worker-class uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:5050
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend static files
    root /path/to/frontend/dist;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # WebSocket proxy to backend
    location /browser-stream {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

### Docker

A `Dockerfile` and `docker-compose.yml` can be added for containerized deployment. The backend runs on port 5050; the frontend is served as static files via nginx or the backend itself.

### Environment Variables for Production

| Variable | Required | Notes |
|---|---|---|
| `GROQ_API_KEY` | Yes | Set via environment, not in `.env` file |
| `LOG_LEVEL` | No | Set to `WARNING` in production |
| `LOG_FORMAT` | No | Use `json` for log aggregation |

**Security**: Never commit `.env` files. Set secrets via environment variables or a secrets manager in production.

## Tech Stack

- **Frontend**: React, TypeScript, Vite, Web Audio API (AudioWorklet)
- **Backend**: Python, FastAPI, Uvicorn, Groq SDK, Edge TTS, pydub
- **Audio**: PCM16, mu-law encoding, AudioWorklet processors
