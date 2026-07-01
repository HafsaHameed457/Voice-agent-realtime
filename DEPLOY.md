# Deploy to Render (Free)

## Step 1: Create Redis on Upstash (Free)
1. Go to https://console.upstash.com
2. Create Redis → Free tier (10k req/day, 256MB)
3. Copy the Redis URL: `redis://default:password@host:port`

## Step 2: Create Backend Web Service
1. Go to https://dashboard.render.com
2. New → **Web Service**
3. Connect GitHub repo
4. Settings:
   - Name: `voice-agent-api`
   - Runtime: Python 3
   - Plan: Free
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn src.main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 120`
5. Add env vars:
```
GROQ_API_KEY=gsk_your_key
REDIS_URL=redis://default:password@upstash-host:port
LOG_LEVEL=INFO
LOG_FORMAT=json
```
6. Click **Create Web Service**

## Step 3: Create Frontend Static Site
1. New → **Static Site**
2. Connect same GitHub repo
3. Settings:
   - Name: `voice-agent-frontend`
   - Build Command: `cd frontend && npm ci && npm run build`
   - Publish Directory: `frontend/dist`
4. Add env var:
```
VITE_API_URL=https://voice-agent-api.onrender.com
```
5. Click **Create Static Site**

## Step 4: Keep Alive (Optional)
Free web service spins down after 15min. Use UptimeRobot (free) to ping:
1. Go to https://uptimerobot.com
2. Add monitor → HTTP(s)
3. URL: `https://voice-agent-api.onrender.com/health`
4. Interval: 5 minutes

## Step 5: Add CORS
If frontend can't reach API, add the frontend URL to `src/main.py`:
```python
allow_origins=["https://voice-agent-frontend.onrender.com"],
```

## Done!
- Backend: `https://voice-agent-api.onrender.com`
- Frontend: `https://voice-agent-frontend.onrender.com`
- Health: `https://voice-agent-api.onrender.com/health`
- Metrics: `https://voice-agent-api.onrender.com/metrics`
