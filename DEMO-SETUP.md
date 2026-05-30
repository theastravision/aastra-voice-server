# Demo setup (no Docker) — Indic Parler-TTS + Whisper + OpenAI conversational bot

Copy the entire `apps/voice-server` folder to your GPU server, then follow these steps in the **server terminal**.

---

## Step 1 — Copy code to the server

**From your Windows PC** (PowerShell), if you have SSH access:

```powershell
scp -r c:\theastravision\apps\voice-server YOUR_USER@YOUR_SERVER_IP:~/aastra-voice
```

Or on the server, clone your repo:

```bash
git clone YOUR_REPO_URL
cd theastravision/apps/voice-server
```

You need this folder structure on the server:

```
~/aastra-voice/
  main.py
  config.py
  auth.py
  engines/
  routers/
  scripts/
  requirements.txt
  .env.example
```

---

## Step 2 — One-command install

On the server:

```bash
cd ~/aastra-voice
chmod +x scripts/*.sh
bash scripts/install-demo.sh
```

**Salad / Docker terminal:** there is often **no `sudo`** — you are already root. The script uses `apt-get` directly. If `apt-get` is also missing, use a CUDA base image that includes Python, or run only the pip steps:

```bash
cd ~/aastra-voice
python3 -m venv .venv && source .venv/bin/activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
cp .env.example .env && nano .env
bash scripts/download-models.sh
bash scripts/run-demo.sh
```

This installs:

- `espeak-ng`, `ffmpeg` (required for Kokoro + MP3)
- Python venv + PyTorch CUDA + **Indic Parler-TTS** + `faster-whisper`
- Downloads **Whisper** and **Parler** weights via Hugging Face (`HF_TOKEN` required)

Install takes **10–20 minutes** the first time (PyTorch + model download).

---

## Step 3 — Add your API keys (no nano/vi needed)

Salad terminals often have **no text editor**. Use one of these:

**Option A — helper script:**

```bash
cd ~/aastra-voice
OPENAI_API_KEY=sk-your-key VOICE_API_KEY=my-secret bash scripts/create-env.sh
```

**Option B — one-shot `cat` (paste your real keys):**

```bash
cd ~/aastra-voice
cat > .env << 'EOF'
VOICE_API_KEY=my-demo-secret-123
OPENAI_API_KEY=sk-your-openai-key-here
OPENAI_MODEL=gpt-4o-mini
STT_PROVIDER=whisper_chunk
TTS_PROVIDER=parler
HF_TOKEN=hf_...
WHISPER_MODEL=large-v3
WHISPER_LANGUAGE=auto
WHISPER_BEAM_SIZE=5
EN_VOICE=af_bella
HI_VOICE=hf_alpha
TTS_OUTPUT_FORMAT=wav
OPENAI_MAX_COMPLETION_TOKENS=128
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
ALLOW_PUBLIC_DEMO=true
STREAM_ALLOW_PUBLIC=true
PORT=8000
HOST=*
EOF
```

**Option C — copy from example then append keys:**

```bash
cp .env.example .env
echo "OPENAI_API_KEY=sk-your-key" >> .env
echo "VOICE_API_KEY=my-secret" >> .env
```

Verify: `cat .env` (do not share this output publicly).

---

## Step 4 — Start the server (keep it running)

Salad’s default shell is **`sh`**, not bash. `source` does not work — use **`.`** or run scripts with **`bash`**:

```bash
cd /workspace/voice-server
. .venv/bin/activate          # note the dot at the start
# OR: bash scripts/run-demo.sh  (recommended)
```

**Foreground** (see logs in terminal):

```bash
cd ~/aastra-voice
bash scripts/run-demo.sh
```

**Background** (keeps running after you disconnect SSH):

```bash
bash scripts/run-demo-background.sh
tail -f ~/aastra-voice/voice-server.log
```

Server listens on **port 8000** by default (`PORT` in `.env`). `/health` returns immediately; `models_ready` becomes `true` after background warmup (~60s).

---

## Step 5 — Open firewall (bare Ubuntu VPS only)

```bash
sudo ufw allow 8000/tcp
sudo ufw reload
```

On Salad web terminal you usually skip this; use their gateway or access via `curl` on localhost first.

---

## Step 6 — Test from the server

```bash
# Health
curl http://127.0.0.1:8000/health
bash scripts/verify-ngrok.sh

# Text-to-speech (Kokoro)
curl -H "Authorization: Bearer my-demo-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, I am Astra. Tell me about yourself.","voice":"astra"}' \
  http://127.0.0.1:8000/api/v1/tts -o test.mp3

# Full conversational turn (Whisper → GPT → Kokoro)
curl -H "Authorization: Bearer my-demo-secret-123" \
  -F "audio=@test.webm" \
  -F "lang_hint=auto" \
  http://127.0.0.1:8000/api/v1/voice-turn
```

Response JSON:

```json
{
  "user_text": "what you said",
  "assistant_text": "GPT reply",
  "assistant_audio_base64": "...",
  "detected_language": "en"
}
```

Decode audio on PC:

```python
import base64, json
data = json.load(open("response.json"))
open("reply.mp3","wb").write(base64.b64decode(data["assistant_audio_base64"]))
```

---

## Step 7 — Test from your Windows PC

Replace `SERVER_IP` with the machine’s public IP:

```powershell
curl http://SERVER_IP:9001/health

curl -H "Authorization: Bearer my-demo-secret-123" `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Hello from my PC.\",\"voice\":\"astra\"}" `
  http://SERVER_IP:9001/api/v1/tts -o reply.mp3
```

---

## All API endpoints (your Python code)

| What | Method | URL |
|------|--------|-----|
| Health | GET | `/health` |
| Speech → text | POST | `/api/v1/transcribe` |
| Text → speech | POST | `/api/v1/tts` |
| **Full voice chat** | POST | `/api/v1/voice-turn` |
| WebSocket (Django) | WS | `/ws/audio` |

Interactive docs: `http://SERVER_IP:9001/docs`

---

## Python files (already included — do not rewrite)

| File | Function |
|------|----------|
| `main.py` | Starts FastAPI, loads `.env` |
| `engines/whisper_stt.py` | Whisper STT |
| `engines/parler_tts.py` | Indic Parler-TTS (Hindi + English) |
| `engines/conversation.py` | OpenAI chat + full `voice_turn()` |
| `routers/http_audio.py` | HTTP routes |
| `routers/ws_audio.py` | WebSocket for AastraaHR |

**Conversational flow** is in `engines/conversation.py` → `voice_turn()`:

1. Whisper transcribes your audio  
2. OpenAI `gpt-5.4-mini` generates reply  
3. Kokoro speaks the reply (English or Hindi based on detected language)

---

## Connect AastraaHR (optional)

On your dev machine `apps/api/.env`:

```env
XYZ_AUDIO_HTTP_BASE_URL=http://YOUR_SERVER_IP:9001
XYZ_AUDIO_API_KEY=my-demo-secret-123
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `CUDA not available` | `nvidia-smi` — install NVIDIA driver; or set `WHISPER_DEVICE=cpu` and `WHISPER_COMPUTE_TYPE=int8` in `.env` |
| First request very slow | Run `bash scripts/download-models.sh` again |
| `espeak-ng not found` | `sudo apt install espeak-ng` |
| Port in use | `PORT=9002 bash scripts/run-demo.sh` |
| OpenAI error | Check `OPENAI_API_KEY` in `.env` |

---

## Stop background server

```bash
kill $(cat ~/aastra-voice/voice-server.pid)
```

---

## Public access via Salad Container Gateway (no ngrok)

Per [Salad networking docs](https://docs.salad.com/container-engine/explanation/infrastructure-platform/networking):

1. Portal → container group → **Container Gateway** → port **9001**
2. Enable **authentication** if you want (recommended)
3. Copy gateway URL: `https://your-group.salad.cloud`
4. Salad API key: Portal → profile → **API Access** → use header `Salad-Api-Key` ([docs](https://docs.salad.com/container-engine/how-to-guides/gateway/sending-requests))

On the container:

```bash
HOST='*' PORT=9001 bash scripts/run-demo-background.sh
curl http://127.0.0.1:8000/health
bash scripts/verify-ngrok.sh
```

From your PC:

```bash
curl https://your-group.salad.cloud/health -H "Salad-Api-Key: YOUR_SALAD_KEY"
```

`apps/api/.env`:

```env
XYZ_AUDIO_HTTP_BASE_URL=https://your-group.salad.cloud
XYZ_SALAD_API_KEY=your-salad-api-key
XYZ_AUDIO_API_KEY=your-voice-api-key-from-container-.env
```

---

## Public access from your PC (ngrok)

Salad does not expose raw IPs. Use **ngrok** (tunnel port must match `PORT` in `.env`, default **8000**):

- **ERR_NGROK_3004**: upstream not responding — wrong port (`ngrok http 8000` not `9001`), server still starting, or crash. Check `curl http://127.0.0.1:8000/health` and wait for `"models_ready": true`.
- Demo UI: `https://YOUR-SUBDOMAIN.ngrok-free.app/bot` (streaming WebSocket + MeloTTS Indian English).

1. Create free account: https://ngrok.com  
2. Copy authtoken: https://dashboard.ngrok.com/get-started/your-authtoken  
3. Add to `.env`:

```bash
echo 'NGROK_AUTHTOKEN=your_token_here' >> .env
```

4. Start voice server + tunnel:

```bash
cd /workspace/voice-server
bash scripts/start-demo-ngrok.sh
cat ngrok-url.txt
```

5. From **Windows** (use URL from `ngrok-url.txt`):

```powershell
curl https://YOUR-SUBDOMAIN.ngrok-free.app/health
```

6. **AastraaHR** `apps/api/.env`:

```env
XYZ_AUDIO_HTTP_BASE_URL=https://YOUR-SUBDOMAIN.ngrok-free.app
XYZ_AUDIO_API_KEY=same-as-VOICE_API_KEY
```

Stop everything:

```bash
bash scripts/stop-demo-ngrok.sh
```
