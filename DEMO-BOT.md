# Demo conversational voice bot

## URLs (ngrok example)

| Page | URL |
|------|-----|
| UI | https://only-recant-salary.ngrok-free.dev/bot |
| Health | https://only-recant-salary.ngrok-free.dev/health |

## Salad `.env` for testing (no auth)

```bash
VOICE_API_KEY=
ALLOW_PUBLIC_DEMO=true
OPENAI_API_KEY=sk-...
PORT=8000
```

Restart voice server after pulling new code.

## Flow

1. **Start** — Hindi greeting: *Hello Aashish, aapka swagat hai.*
2. **Turn** — You speak; Astra replies (Hindi/English).
3. **End** — Say *alvida* / *bye* or tap **End call**.

## Interview (Django)

`apps/api/.env`:

```env
XYZ_AUDIO_HTTP_BASE_URL=https://only-recant-salary.ngrok-free.dev
XYZ_AUDIO_API_KEY=
```

## Admin web

`apps/admin-web/.env.local`:

```env
NEXT_PUBLIC_VOICE_BOT_URL=https://only-recant-salary.ngrok-free.dev
```

Open: http://localhost:3000/demo/voice-bot
