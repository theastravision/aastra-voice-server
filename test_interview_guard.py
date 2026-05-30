"""Tests for interview strict-mode guardrails."""

import pytest


@pytest.fixture
def strict_guard(monkeypatch):
    monkeypatch.setenv('BOT_MODE', 'interview')
    monkeypatch.setenv('INTERVIEW_STRICT_MODE', 'true')
    from importlib import reload
    import config
    import engines.interview_guard as guard

    reload(config)
    reload(guard)
    return guard


def test_off_topic_llm_question(strict_guard):
    assert strict_guard.is_off_topic_interview_question('What LLM model do you use?')
    assert strict_guard.is_off_topic_interview_question('Tell me about your backend architecture')
    assert strict_guard.is_off_topic_interview_question('Aap ka backend kya hai?')


def test_allows_candidate_backend_experience(strict_guard):
    assert not strict_guard.is_off_topic_interview_question(
        'I built backend services using Python and PostgreSQL for five years.'
    )


def test_disabled_when_strict_mode_off(monkeypatch):
    monkeypatch.setenv('BOT_MODE', 'interview')
    monkeypatch.setenv('INTERVIEW_STRICT_MODE', 'false')
    from importlib import reload
    import config
    import engines.interview_guard as guard

    reload(config)
    reload(guard)
    assert not guard.is_off_topic_interview_question('What LLM do you use?')


def test_refusal_messages():
    from engines.interview_guard import off_topic_refusal_message

    en, script = off_topic_refusal_message('en', 'en')
    assert 'interview' in en.lower()
    assert 'backend' in en.lower()
    assert script == 'en'

    hi, script_hi = off_topic_refusal_message('hi', 'hi')
    assert 'backend' in hi.lower()
    assert script_hi == 'hi'
