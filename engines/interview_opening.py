"""Phased interview opening: guidelines, name capture, welcome, intro request."""

from __future__ import annotations

import re
from enum import Enum

from config import BOT_MODE, INTERVIEW_JOB_TITLE, INTERVIEW_OPENING_ENABLED
from engines.lang_detect import ReplyScript, SessionLanguage
from engines.llm_script_contract import uses_devanagari_output
from engines.stt_names import closest_name

_NAME_PATTERNS = (
    re.compile(
        r"(?:my name is|i am|i'm|this is|call me|name is)\s+([A-Za-z][A-Za-z\s'\-]{0,40})",
        re.I,
    ),
    re.compile(
        r"(?:mera naam|mera name|naam|name)\s+(?:hai\s+)?([A-Za-z][A-Za-z\s'\-]{0,40})",
        re.I,
    ),
    re.compile(
        r"main\s+([A-Za-z][A-Za-z\s'\-]{0,30})\s+hoon",
        re.I,
    ),
)

_NOT_NAME_WORDS = frozenset(
    {
        'hello',
        'hi',
        'hey',
        'yes',
        'no',
        'ok',
        'okay',
        'thanks',
        'thank',
        'namaste',
        'haan',
        'hai',
        'hoon',
        'nahi',
        'the',
        'and',
        'interview',
        'candidate',
    }
)


class InterviewPhase(str, Enum):
    WAITING_NAME = 'waiting_name'
    AWAIT_INTRO = 'await_intro'
    ACTIVE = 'active'


def interview_opening_enabled() -> bool:
    return BOT_MODE == 'interview' and INTERVIEW_OPENING_ENABLED


def initial_interview_phase() -> InterviewPhase:
    if interview_opening_enabled():
        return InterviewPhase.WAITING_NAME
    return InterviewPhase.ACTIVE


def _reply_script(session_lang: SessionLanguage | None) -> ReplyScript:
    if session_lang == 'hi':
        return 'hi'
    if session_lang == 'hinglish':
        return 'hinglish'
    return 'en'


def opening_script(session_lang: SessionLanguage | None) -> tuple[str, ReplyScript]:
    """Guidelines + ask for candidate name."""
    script = _reply_script(session_lang)
    devanagari = uses_devanagari_output()
    if script == 'hi':
        if devanagari:
            text = (
                'नमस्ते, मैं Astra हूँ। शुरू करने से पहले: अपनी screen share on रखें '
                'और camera हमेशा on रखें। Screen split या extra tabs mat kholiye. '
                'अगर कुछ गलत दिखा तो interview pause हो सकती है। '
                'Interview ke bahar sawaal mat poochiye. कृपया अपना naam बताइए।'
            )
        else:
            text = (
                'Namaste, main Astra hoon. Shuru karne se pehle: apni screen share rakhein '
                'aur camera hamesha on rakhein. Screen split ya doosre tabs mat kholiye. '
                'Agar kuch galat dikha toh interview pause ho sakti hai. '
                'Interview ke bahar sawaal mat poochiye. Aap apna naam batayiye.'
            )
    elif script == 'hinglish':
        if devanagari:
            text = (
                'नमस्ते, मैं Astra हूँ। शुरू करने से पहले, screen share on रखें '
                'और camera हमेशा on रखें। Screen split या extra tabs mat kholiye. '
                'अगर कुछ गलत दिखा तो interview pause हो सकती है। '
                'Interview ke bahar sawaal mat poochiye. कृपया अपना naam बताइए।'
            )
        else:
            text = (
                'Namaste, main Astra hoon. Shuru karne se pehle: screen share on rakhein '
                'aur camera hamesha on rakhein. Screen split ya extra tabs mat kholiye. '
                'Agar kuch galat dikha toh interview pause ho sakti hai. '
                'Interview ke bahar sawaal mat poochiye. Aap apna naam batayiye.'
            )
    else:
        text = (
            'Hello, I am Astra. Before we begin: keep your screen shared and camera on '
            'at all times. Do not split your screen or open other tabs. '
            'If we notice anything unusual we may pause the interview. '
            'Please do not ask questions outside the interview context. '
            'What is your name?'
        )
    return text, script


def name_retry_script(session_lang: SessionLanguage | None) -> tuple[str, ReplyScript]:
    script = _reply_script(session_lang)
    devanagari = uses_devanagari_output()
    if script == 'hi':
        if devanagari:
            return (
                'माफ़ कीजिए, मैं आपका naam नहीं सुन पाई। कृपया अपना पूरा naam बोलिए।',
                script,
            )
        return (
            'Maaf kijiye, main aapka naam sun nahi payi. Kripya apna poora naam boliye.',
            script,
        )
    if script == 'hinglish':
        if devanagari:
            return (
                'Sorry, मैं आपका naam नहीं सुन पाई। Please अपना full naam बोलिए।',
                script,
            )
        return (
            'Sorry, main aapka naam sun nahi payi. Please apna full naam boliye.',
            script,
        )
    return (
        'Sorry, I did not catch your name. Please say your full name.',
        script,
    )


def welcome_and_intro_script(
    name: str | None,
    session_lang: SessionLanguage | None,
) -> tuple[str, ReplyScript]:
    script = _reply_script(session_lang)
    display = (name or '').strip().title() or None
    role = INTERVIEW_JOB_TITLE
    devanagari = uses_devanagari_output()
    if script == 'hi':
        if devanagari:
            if display:
                text = (
                    f'Welcome {display}. मैं आज आपका {role} role के लिए interview लूँगी। '
                    f'अपने बारे में thoda बताइए।'
                )
            else:
                text = (
                    f'Welcome. मैं आज आपका {role} role के लिए interview लूँगी। '
                    f'अपने बारे में thoda बताइए।'
                )
        elif display:
            text = (
                f'Welcome {display}. Main aaj aapka {role} pad ke liye interview lungi. '
                f'Apne baare mein thoda batayiye.'
            )
        else:
            text = (
                f'Welcome. Main aaj aapka {role} pad ke liye interview lungi. '
                f'Apne baare mein thoda batayiye.'
            )
    elif script == 'hinglish':
        if devanagari:
            if display:
                text = (
                    f'Welcome {display}. मैं आज आपका {role} role के लिए interview लूँगी। '
                    f'अपने बारे में thoda बताइए।'
                )
            else:
                text = (
                    f'Welcome. मैं आज आपका {role} role के लिए interview लूँगी। '
                    f'अपने बारे में thoda बताइए।'
                )
        elif display:
            text = (
                f'Welcome {display}. Main aaj aapka {role} role ke liye interview lungi. '
                f'Apne baare mein thoda batayiye.'
            )
        else:
            text = (
                f'Welcome. Main aaj aapka {role} role ke liye interview lungi. '
                f'Apne baare mein thoda batayiye.'
            )
    else:
        if display:
            text = (
                f'Welcome {display}. I will conduct your {role} interview today. '
                f'Please tell me a little about yourself.'
            )
        else:
            text = (
                f'Welcome. I will conduct your {role} interview today. '
                f'Please tell me a little about yourself.'
            )
    return text, script


def _clean_name(raw: str) -> str | None:
    cleaned = re.sub(r"[^A-Za-z\s'\-]", ' ', raw).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    if not cleaned:
        return None
    parts = cleaned.split()
    while parts and parts[-1].lower() in _NOT_NAME_WORDS:
        parts.pop()
    while parts and parts[0].lower() in _NOT_NAME_WORDS:
        parts.pop(0)
    if not parts:
        return None
    name = ' '.join(parts[:3]).title()
    corrected = closest_name(name)
    if corrected:
        name = corrected
    if name.lower() in _NOT_NAME_WORDS:
        return None
    if len(name) < 2:
        return None
    return name


def extract_candidate_name(text: str) -> str | None:
    """Parse spoken name from STT transcript."""
    cleaned = (text or '').strip()
    if not cleaned:
        return None
    for pattern in _NAME_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            name = _clean_name(match.group(1))
            if name:
                return name
    words = cleaned.split()
    if 1 <= len(words) <= 3 and len(cleaned) <= 40:
        if all(re.match(r"^[A-Za-z][A-Za-z'\-]*$", w) for w in words):
            name = _clean_name(cleaned)
            if name:
                return name
    return None


INTRO_FOLLOW_UP_HINT = (
    'The candidate just shared their introduction. '
    'Ask ONE specific follow-up question based on what they said '
    '(role, stack, project, or years of experience).'
)
