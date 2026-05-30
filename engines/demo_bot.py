"""In-memory demo conversational bot (no auth) for testing."""

from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from config import BOT_MODE, INTERVIEW_JOB_TITLE, OPENAI_VOICE_TEMPERATURE
from engines.conversation import chat_reply
from engines.f5_tts_engine import synthesize_audio
from engines.lang_detect import (
    ReplyScript,
    SessionLanguage,
    pick_reply_script_for_session,
    pick_tts_route_for_session,
    pick_tts_route_from_text,
    resolve_session_language,
    resolve_whisper_language,
)
from engines.llm_script_contract import (
    script_retry_message,
    should_strict_script_gate,
    validate_assistant_script,
)
from engines.llm_turn import build_extra_system
from engines.interview_opening import (
    INTRO_FOLLOW_UP_HINT,
    InterviewPhase,
    extract_candidate_name,
    initial_interview_phase,
    interview_opening_enabled,
    name_retry_script,
    opening_script,
    welcome_and_intro_script,
)
from streaming.prompts import VERBAL_VOICE_SYSTEM_PROMPT
from streaming.prompts_interviewer import interviewer_system_prompt

END_CALL_PATTERNS = re.compile(
    r'\b(bye|goodbye|end call|hang up|alvida|अलविदा|बाय|कॉल खत्म|'
    r'कॉल बंद|समाप्त|stop call|disconnect)\b',
    re.IGNORECASE,
)


@dataclass
class DemoSession:
    session_id: str
    candidate_name: str
    session_language: SessionLanguage | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    ended: bool = False
    last_reply_script: str = 'en'
    interview_phase: InterviewPhase = field(default_factory=initial_interview_phase)
    name_retry_used: bool = False
    intro_captured: bool = False


_sessions: dict[str, DemoSession] = {}


def _system_prompt(candidate_name: str) -> str:
    if BOT_MODE == 'interview':
        base = interviewer_system_prompt()
        return f'{base}\nThe candidate\'s name is {candidate_name}.'
    return f'{VERBAL_VOICE_SYSTEM_PROMPT}\nThe caller\'s name is {candidate_name}.'


def _greeting_text(name: str, session_lang: SessionLanguage | None) -> tuple[str, ReplyScript]:
    role = INTERVIEW_JOB_TITLE
    candidate = (name or 'Candidate').strip() or 'Candidate'
    if session_lang == 'hi':
        return (
            f'Namaste {candidate}, main Astra hoon. '
            f'Main aaj aapka {role} pad ke liye technical interview lungi. '
            f'Chaliye shuru karte hain — apne baare mein thoda batayiye.',
            'hi',
        )
    if session_lang == 'hinglish':
        if BOT_MODE == 'interview':
            return (
                f'Namaste {candidate}, main Astra hoon. '
                f'Main aaj aapka technical interview lungi {role} position ke liye. '
                f'Chaliye shuru karte hain — apne baare mein thoda batayiye.',
                'hinglish',
            )
        return f'Namaste {candidate}, aapka swagat hai.', 'hinglish'
    if BOT_MODE == 'interview':
        return (
            f'Hello {candidate}, I am Astra. '
            f'I will conduct your technical interview today for the {role} role. '
            f'Let us begin — please tell me a little about yourself.',
            'en',
        )
    return f'Hello {candidate}, welcome.', 'en'


def _audio_payload(text: str, *, reply_script: str = 'en') -> dict[str, str | None]:
    audio, mime = synthesize_audio(text)
    return {
        'assistant_text': text,
        'assistant_audio_base64': base64.b64encode(audio).decode('ascii'),
        'mime': mime,
    }


def start_session(
    candidate_name: str = 'Aashish',
    *,
    language: str | None = 'en',
) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    session_lang = resolve_session_language(language)
    if interview_opening_enabled():
        greeting, script = opening_script(session_lang)
        name = ''
    else:
        name = (candidate_name or 'Aashish').strip() or 'Aashish'
        greeting, script = _greeting_text(name, session_lang)
    session = DemoSession(
        session_id=session_id,
        candidate_name=name,
        session_language=session_lang,
        last_reply_script=script,
    )
    session.history.append({'role': 'assistant', 'content': greeting})
    _sessions[session_id] = session
    payload = _audio_payload(greeting, reply_script=script)
    return {
        'session_id': session_id,
        'candidate_name': name or None,
        'session_language': language or 'auto',
        'ended': False,
        'detected_language': script,
        'interview_phase': session.interview_phase.value,
        **payload,
    }


def end_session(session_id: str) -> dict[str, Any]:
    session = _sessions.get(session_id)
    if not session:
        return {'session_id': session_id, 'ended': True, 'error': 'Session not found.'}
    session.ended = True
    script = session.last_reply_script
    if script == 'en':
        goodbye = f'Thank you {session.candidate_name}. Have a great day. Goodbye.'
    elif script == 'hi':
        goodbye = f'धन्यवाद {session.candidate_name}। आपका दिन शुभ हो। अलविदा।'
    else:
        goodbye = f'Thank you {session.candidate_name}, aapka din shubh ho. Alvida.'
    session.history.append({'role': 'assistant', 'content': goodbye})
    payload = _audio_payload(goodbye, reply_script=script)
    return {'session_id': session_id, 'ended': True, **payload}


def process_turn(
    session_id: str,
    audio_bytes: bytes,
    *,
    filename: str = 'audio.webm',
) -> dict[str, Any]:
    from engines.whisper_stt import transcribe_bytes

    session = _sessions.get(session_id)
    if not session:
        return {'session_id': session_id, 'error': 'Session not found.', 'ended': True}
    if session.ended:
        return {'session_id': session_id, 'ended': True, 'error': 'Call already ended.'}

    whisper_lang = resolve_whisper_language(
        session.session_language if session.session_language else 'auto'
    )
    stt = transcribe_bytes(
        audio_bytes, filename=filename, language=whisper_lang
    )
    user_text = (stt.get('text') or '').strip()
    detected = stt.get('detected_language', 'hi')
    reply_script = pick_reply_script_for_session(
        session.session_language, detected, user_text
    )
    session.last_reply_script = reply_script

    if not user_text:
        if reply_script == 'en':
            msg = 'Sorry, I did not catch that. Please say it again.'
        elif reply_script == 'hi':
            msg = 'माफ़ कीजिए, मैं सुन नहीं पाई। कृपया दोबारा बोलिए।'
        else:
            msg = 'Sorry, main sun nahi payi. Kripya dobara boliye.'
        return {
            'session_id': session_id,
            'user_text': '',
            'detected_language': detected,
            'reply_language': reply_script,
            'ended': False,
            **_audio_payload(msg, reply_script=reply_script),
        }

    if END_CALL_PATTERNS.search(user_text):
        session.ended = True
        if reply_script == 'en':
            goodbye = f'Okay {session.candidate_name}, ending the call. Goodbye!'
        elif reply_script == 'hi':
            goodbye = f'ठीक है {session.candidate_name}, कॉल समाप्त करती हूँ। अलविदा!'
        else:
            goodbye = f'Theek hai {session.candidate_name}, call samapt karti hoon. Alvida!'
        session.history.append({'role': 'user', 'content': user_text})
        session.history.append({'role': 'assistant', 'content': goodbye})
        return {
            'session_id': session_id,
            'user_text': user_text,
            'detected_language': detected,
            'reply_language': reply_script,
            'ended': True,
            **_audio_payload(goodbye, reply_script=reply_script),
        }

    session.history.append({'role': 'user', 'content': user_text})

    from engines.interview_guard import (
        is_off_topic_interview_question,
        off_topic_refusal_message,
    )

    if session.interview_phase == InterviewPhase.WAITING_NAME:
        name = extract_candidate_name(user_text)
        if name:
            session.candidate_name = name
            assistant_text, script = welcome_and_intro_script(name, session.session_language)
            session.interview_phase = InterviewPhase.AWAIT_INTRO
        elif not session.name_retry_used:
            session.name_retry_used = True
            assistant_text, script = name_retry_script(session.session_language)
        else:
            assistant_text, script = welcome_and_intro_script(None, session.session_language)
            session.interview_phase = InterviewPhase.AWAIT_INTRO
        session.history.append({'role': 'assistant', 'content': assistant_text})
        tts_route = pick_tts_route_for_session(session.session_language, script)
        return {
            'session_id': session_id,
            'user_text': user_text,
            'detected_language': detected,
            'reply_language': script,
            'interview_phase': session.interview_phase.value,
            'ended': False,
            **_audio_payload(assistant_text, reply_script=tts_route),
        }

    intro_follow_up = False
    if session.interview_phase == InterviewPhase.AWAIT_INTRO:
        session.interview_phase = InterviewPhase.ACTIVE
        session.intro_captured = True
        intro_follow_up = True

    if is_off_topic_interview_question(user_text):
        refusal, script = off_topic_refusal_message(session.session_language, reply_script)
        session.history.append({'role': 'assistant', 'content': refusal})
        tts_route = pick_tts_route_for_session(session.session_language, script)
        return {
            'session_id': session_id,
            'user_text': user_text,
            'detected_language': detected,
            'reply_language': script,
            'interview_phase': session.interview_phase.value,
            'ended': False,
            **_audio_payload(refusal, reply_script=tts_route),
        }

    extra = build_extra_system(
        session.session_language,
        reply_script,
        intro_follow_up=INTRO_FOLLOW_UP_HINT if intro_follow_up else None,
    )
    prompt_name = session.candidate_name or 'Candidate'
    assistant_text = chat_reply(
        user_text,
        history=session.history[:-1],
        system_prompt=_system_prompt(prompt_name),
        extra_system=extra,
        temperature=OPENAI_VOICE_TEMPERATURE,
    )
    if (
        should_strict_script_gate()
        and session.session_language in ('hi', 'hinglish')
        and assistant_text
        and not validate_assistant_script(assistant_text, session.session_language)
    ):
        assistant_text = chat_reply(
            script_retry_message(session.session_language),
            history=session.history,
            system_prompt=_system_prompt(prompt_name),
            extra_system=extra,
            temperature=OPENAI_VOICE_TEMPERATURE,
        )
    session.history.append({'role': 'assistant', 'content': assistant_text})
    tts_route = pick_tts_route_for_session(session.session_language, reply_script)
    if session.session_language is None:
        tts_route = pick_tts_route_from_text(assistant_text, fallback=reply_script)
    return {
        'session_id': session_id,
        'user_text': user_text,
        'detected_language': detected,
        'reply_language': reply_script,
        'interview_phase': session.interview_phase.value,
        'ended': False,
        **_audio_payload(assistant_text, reply_script=tts_route),
    }
