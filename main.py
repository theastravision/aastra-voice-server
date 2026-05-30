"""AastraaHR GPU voice server — F5-TTS + faster-whisper STT + GPT conversational turns."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / '.env')
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from routers import bot_demo, http_audio, training, voices, ws_audio, ws_stream

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from core.model_state import run_warmup_background
    from streaming.event_bus import get_event_bus

    run_warmup_background()
    bus = get_event_bus()
    await bus.start()
    yield
    await bus.stop()
    logger.info('Voice server shutting down')


app = FastAPI(
    title='AastraaHR Voice Server',
    version='1.1.0',
    description='F5-TTS + faster-whisper STT; OpenAI dialogue; Hindi/English/Hinglish',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(ws_audio.router)
app.include_router(ws_stream.router)
app.include_router(http_audio.router)
app.include_router(bot_demo.router)
app.include_router(voices.router)
app.include_router(training.router)

_static_dir = Path(__file__).resolve().parent / 'static'
if _static_dir.is_dir():
    app.mount('/static', StaticFiles(directory=str(_static_dir)), name='static')

_data_root = Path(__file__).resolve().parent / 'data'
_name_samples_dir = _data_root / 'name-samples'
if _name_samples_dir.is_dir():
    app.mount(
        '/data/name-samples',
        StaticFiles(directory=str(_name_samples_dir)),
        name='name-samples',
    )
_voice_samples_dir = _data_root / 'voice-samples'
if _voice_samples_dir.is_dir():
    app.mount(
        '/data/voice-samples',
        StaticFiles(directory=str(_voice_samples_dir)),
        name='voice-samples',
    )

_interview_dist = Path(__file__).resolve().parent / 'interview-ui' / 'dist'


@app.get('/stream')
def stream_demo_page():
    return RedirectResponse(url='/bot', status_code=302)


@app.get('/bot')
def bot_demo_page():
    from config import ALLOW_PUBLIC_DEMO, DEMO_CANDIDATE_NAME, STT_PROVIDER, TTS_PROVIDER
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    if not ALLOW_PUBLIC_DEMO:
        raise HTTPException(status_code=403, detail='Demo disabled')
    path = Path(__file__).resolve().parent / 'static' / 'bot-demo.html'
    return FileResponse(
        path,
        media_type='text/html',
        headers={
            'X-Demo-Candidate-Name': DEMO_CANDIDATE_NAME,
            'X-Stt-Provider': STT_PROVIDER,
            'X-Tts-Provider': TTS_PROVIDER,
        },
    )


@app.get('/bot/names')
def bot_name_samples_page():
    from config import ALLOW_PUBLIC_DEMO
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    if not ALLOW_PUBLIC_DEMO:
        raise HTTPException(status_code=403, detail='Demo disabled')
    path = Path(__file__).resolve().parent / 'static' / 'name-samples.html'
    if not path.is_file():
        raise HTTPException(status_code=404, detail='Name samples UI missing')
    return FileResponse(path, media_type='text/html')


@app.get('/interview', include_in_schema=False)
def interview_ui_redirect():
    """Redirect to trailing slash so Vite assets resolve under /interview/."""
    from config import ALLOW_PUBLIC_DEMO
    from fastapi import HTTPException

    if not ALLOW_PUBLIC_DEMO:
        raise HTTPException(status_code=403, detail='Demo disabled')
    if not (_interview_dist / 'index.html').is_file():
        return RedirectResponse(url='/bot', status_code=302)
    return RedirectResponse(url='/interview/', status_code=307)


if (_interview_dist / 'index.html').is_file():
    app.mount(
        '/interview',
        StaticFiles(directory=str(_interview_dist), html=True),
        name='interview-ui',
    )


@app.get('/')
@app.get('/health')
def health():
    from core.model_state import models_ready, warmup_error

    return {
        'status': 'healthy',
        'service': 'aastra-voice-server',
        'models_ready': models_ready(),
        'warmup_error': warmup_error(),
        'streaming_ws': '/ws/voice',
        'bot_ui': '/bot',
        'interview_ui': '/interview',
    }


if __name__ == '__main__':
    import uvicorn

    host = os.environ.get('HOST', '*')
    port = int(os.environ.get('PORT', '8000'))
    uvicorn.run('main:app', host=host, port=port, reload=False)
