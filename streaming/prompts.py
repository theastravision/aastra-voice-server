"""LLM prompts optimized for verbal TTS playback (no markdown/emojis)."""

from __future__ import annotations

from config import BOT_MODE

VERBAL_VOICE_SYSTEM_PROMPT = """You are Astra, a warm female voice assistant on a live phone-style call.
You speak Hindi, English, and Hinglish naturally — match the user's language mix.

STRICT OUTPUT RULES FOR VOICE:
- Write only words that should be spoken aloud.
- Never use markdown, bullet points, numbered lists, emojis, or asterisks.
- Keep each turn to one or two short conversational sentences.
- Spell out numbers and metrics in words (say "fifty percent" not "50%").
- Avoid parentheses, URLs, and abbreviations unless you spell them letter by letter.
- For Hindi use Devanagari; for English use Latin script; for Hinglish mix naturally.
- Do not say you are an AI unless asked.
"""

VERBAL_USER_PREFIX = "User said (transcribed): "


def build_messages(
    *,
    history: list[dict[str, str]],
    user_text: str,
    extra_system: str | None = None,
    candidate_name: str | None = None,
) -> list[dict[str, str]]:
    if BOT_MODE == 'interview':
        from streaming.prompts_interviewer import build_interview_messages

        return build_interview_messages(
            history=history,
            user_text=user_text,
            extra_system=extra_system,
            candidate_name=candidate_name,
        )
    system = VERBAL_VOICE_SYSTEM_PROMPT
    if candidate_name:
        system = f'{system}\nThe caller\'s name is {candidate_name.strip()}.'
    if extra_system:
        system = f'{system}\n{extra_system}'
    messages: list[dict[str, str]] = [{'role': 'system', 'content': system}]
    for item in history:
        role = item.get('role', 'user')
        content = (item.get('content') or '').strip()
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content[:2000]})
    messages.append({'role': 'user', 'content': f'{VERBAL_USER_PREFIX}{user_text[:2000]}'})
    return messages
