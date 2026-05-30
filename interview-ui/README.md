# Astra Interview UI (React)

## Dev (one command)

From `apps/voice-server`:

```bash
bash scripts/run-local-dev.sh
```

| Service | URL |
|---------|-----|
| Bot (HTML) | http://localhost:8000/bot |
| React interview UI | http://localhost:5173 |
| Health | http://localhost:8000/health |

Stop: `Ctrl+C` or `bash scripts/stop-local-dev.sh`

## Dev (two terminals, manual)

**Terminal 1 — voice server (port 8000):**

```bash
cd apps/voice-server
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Vite (proxies `/ws` and `/api` to 8000):**

```bash
cd apps/voice-server/interview-ui
npm install
npm run dev
```

## Production build

```bash
cd apps/voice-server/interview-ui
npm run build
```

Then open http://localhost:8000/interview (serves `dist/` when built).

## Bot demo (no React)

http://localhost:8000/bot — same Parler + Whisper stack, HTML UI.
