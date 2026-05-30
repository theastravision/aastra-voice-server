"""Tests for phased interview opening flow."""

from engines.interview_opening import (
    InterviewPhase,
    extract_candidate_name,
    initial_interview_phase,
    name_retry_script,
    opening_script,
    welcome_and_intro_script,
)


def test_opening_script_contains_guidelines_en():
    text, script = opening_script('en')
    assert script == 'en'
    assert 'screen' in text.lower()
    assert 'camera' in text.lower()
    assert 'tabs' in text.lower()
    assert 'name' in text.lower()


def test_opening_script_contains_guidelines_hi():
    text, script = opening_script('hi')
    assert script == 'hi'
    assert 'screen' in text.lower()
    assert 'camera' in text.lower()
    assert 'naam' in text.lower()


def test_extract_name_english():
    assert extract_candidate_name('My name is Azush') == 'Azush'
    assert extract_candidate_name('I am Rahul Kumar') == 'Rahul Kumar'
    assert extract_candidate_name('Azush') == 'Azush'


def test_extract_name_hinglish():
    assert extract_candidate_name('Mera naam Priya hai') == 'Priya'
    assert extract_candidate_name('Main Aashish hoon') == 'Aashish'


def test_welcome_uses_name():
    text, script = welcome_and_intro_script('Azush', 'en')
    assert 'Azush' in text
    assert 'about yourself' in text.lower()
    assert script == 'en'


def test_welcome_without_name():
    text, _script = welcome_and_intro_script(None, 'en')
    assert 'Welcome.' in text
    assert 'about yourself' in text.lower()


def test_name_retry_scripts():
    en, _ = name_retry_script('en')
    hi, _ = name_retry_script('hi')
    assert 'name' in en.lower()
    assert 'naam' in hi.lower()


def test_initial_phase_active_when_disabled(monkeypatch):
    monkeypatch.setenv('INTERVIEW_OPENING_ENABLED', 'false')
    from importlib import reload
    import config
    import engines.interview_opening as opening

    reload(config)
    reload(opening)
    assert opening.initial_interview_phase() == InterviewPhase.ACTIVE
