"""OpenAI chat for conversational voice turns."""

from __future__ import annotations

import json
import logging
from typing import Any

from config import (
    CHAT_HISTORY_MAX_TURNS,
    INTERVIEWER_SYSTEM_PROMPT,
    OPENAI_API_KEY,
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_MODEL,
    OPENAI_VOICE_TEMPERATURE,
)
from engines.openai_chat import create_chat_completion

logger = logging.getLogger(__name__)



def chat_reply(
    user_text: str,
    *,
    history: list[dict[str, str]] | None = None,
    extra_system: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY is not configured.')
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    system = system_prompt or INTERVIEWER_SYSTEM_PROMPT
    if extra_system:
        system = f'{system}\n{extra_system}'
    messages: list[dict[str, str]] = [{'role': 'system', 'content': system}]
    trimmed = list(history or [])[-CHAT_HISTORY_MAX_TURNS * 2 :]
    for item in trimmed:
        role = item.get('role', 'user')
        content = item.get('content', '')
        if role in ('user', 'assistant', 'system') and content:
            messages.append({'role': role, 'content': str(content)[:4000]})
    messages.append({'role': 'user', 'content': user_text[:4000]})
    response = create_chat_completion(
        client,
        model=OPENAI_MODEL,
        messages=messages,
        max_output_tokens=OPENAI_MAX_COMPLETION_TOKENS,
        temperature=temperature if temperature is not None else OPENAI_VOICE_TEMPERATURE,
    )
    return (response.choices[0].message.content or '').strip()


def parse_history_json(raw: str | None) -> list[dict[str, str]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError('history must be valid JSON array') from exc
    if not isinstance(data, list):
        raise ValueError('history must be a JSON array')
    return data


def voice_turn(
    audio_bytes: bytes,
    *,
    filename: str = 'audio.webm',
    lang_hint: str | None = 'auto',
    history: list[dict[str, str]] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    from engines.f5_tts_engine import synthesize_audio
    from engines.whisper_stt import transcribe_bytes

    stt = transcribe_bytes(
        audio_bytes,
        filename=filename,
        language=None if lang_hint in (None, 'auto') else lang_hint,
    )
    user_text = stt['text']
    detected = stt['detected_language']
    if not user_text:
        return {
            'session_id': session_id,
            'user_text': '',
            'assistant_text': '',
            'assistant_audio_base64': None,
            'mime': 'audio/mpeg',
            'detected_language': detected,
            'error': 'No speech detected.',
        }
    assistant_text = chat_reply(user_text, history=history)
    audio_mp3, mime = synthesize_audio(assistant_text)
    import base64

    return {
        'session_id': session_id,
        'user_text': user_text,
        'assistant_text': assistant_text,
        'assistant_audio_base64': base64.b64encode(audio_mp3).decode('ascii'),
        'mime': mime,
        'detected_language': detected,
    }
