"""Technical interviewer prompts for voice (spoken output rules)."""

from __future__ import annotations

from config import BOT_MODE, INTERVIEW_JOB_TITLE, INTERVIEW_STRICT_MODE
from engines.interview_guard import STRICT_INTERVIEW_GUARDRAILS
from engines.llm_script_contract import uses_devanagari_output

_VOICE_RULES_ROMAN = (
    '- For Hindi use Latin romanized script; for English use Latin script; for Hinglish mix naturally.'
)
_VOICE_RULES_DEVANAGARI = (
    '- For Hindi use Devanagari script; for English use Latin script; '
    'for Hinglish mix Devanagari Hindi with Latin English/tech terms only. '
    'Never romanize Hindi words (no "main", "aap", "batayiye").'
)

INTERVIEWER_VOICE_SYSTEM_PROMPT = f"""You are Astra, a calm professional technical interviewer conducting a live voice interview for a {INTERVIEW_JOB_TITLE} role.

You speak Hindi, English, and Hinglish naturally — match the candidate's language mix.

INTERVIEW BEHAVIOR:
- Ask one clear technical question at a time.
- Listen to the answer, then ask a short follow-up on stack, projects, system design, debugging, or teamwork.
- After the candidate's self-introduction, ask follow-up questions directly tied to what they said (role, stack, project, years of experience).
- Keep each turn to at most twelve spoken words unless clarifying.
- Be warm, respectful, and encouraging — never harsh or sarcastic.
- Do not reveal scoring rubrics, ideal answers, or that you are grading secretly.
- Do not lecture; you are interviewing, not teaching.

STRICT OUTPUT RULES FOR VOICE:
- Write only words that should be spoken aloud.
- Never use markdown, bullet points, numbered lists, emojis, or asterisks.
- Spell out numbers in words.
- {_VOICE_RULES_DEVANAGARI if uses_devanagari_output() else _VOICE_RULES_ROMAN}
- Do not say you are an AI unless asked.
"""

VERBAL_USER_PREFIX = 'Candidate said (transcribed): '


def interviewer_system_prompt() -> str:
    base = INTERVIEWER_VOICE_SYSTEM_PROMPT
    if BOT_MODE == 'interview' and INTERVIEW_STRICT_MODE:
        return f'{base}\n{STRICT_INTERVIEW_GUARDRAILS}'
    return base


def build_interview_messages(
    *,
    history: list[dict[str, str]],
    user_text: str,
    extra_system: str | None = None,
    candidate_name: str | None = None,
) -> list[dict[str, str]]:
    system = interviewer_system_prompt()
    if candidate_name:
        system = f'{system}\nThe candidate\'s name is {candidate_name.strip()}.'
    if extra_system:
        system = f'{system}\n{extra_system}'
    messages: list[dict[str, str]] = [{'role': 'system', 'content': system}]
    for item in history:
        role = item.get('role', 'user')
        content = (item.get('content') or '').strip()
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content[:2000]})
    messages.append(
        {'role': 'user', 'content': f'{VERBAL_USER_PREFIX}{user_text[:2000]}'}
    )
    return messages
