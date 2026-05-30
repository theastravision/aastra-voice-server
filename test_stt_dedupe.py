"""Tests for STT dedupe and repeat-intent guardrails."""

from __future__ import annotations

from engines.stt_filters import dedupe_repeated_sentences, is_repeat_intent


def test_dedupe_repeated_sentences():
    raw = 'My name is Alex. My name is Alex. My name is Alex.'
    assert dedupe_repeated_sentences(raw) == 'My name is Alex.'


def test_repeat_intent_not_on_name_answer():
    assert not is_repeat_intent(
        'My name is Alex. My name is Alex. Yes, repeat the question.'
    )


def test_dedupe_repeated_halves():
    raw = (
        'Okay, I have experience with the Python. '
        'Okay, I have experience with the Python.'
    )
    assert dedupe_repeated_sentences(raw).count('Python') == 1


def test_correct_awish_to_ashish():
    from engines.stt_names import correct_names_in_transcript

    assert 'Ashish' in correct_names_in_transcript('My name is Awish')
    assert correct_names_in_transcript('Awish') == 'Ashish'


def test_correct_asheesh_to_ashish():
    from engines.stt_names import correct_names_in_transcript

    assert 'Ashish' in correct_names_in_transcript('My name is Asheesh')
    assert correct_names_in_transcript('Asheesh') == 'Ashish'
