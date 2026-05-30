"""Tests for LLM-first Devanagari script contract and TTS fast path."""

from engines.llm_script_contract import (
    llm_language_hint_strict,
    output_script_for_session,
    system_script_rules,
    validate_assistant_script,
)
from engines.tts_text_pipeline import normalize_mixed_script, prepare_text_for_tts


def test_output_script_hinglish_devanagari():
    assert output_script_for_session('hinglish') == 'devanagari'
    assert output_script_for_session('en') == 'en'


def test_validate_compliant_hinglish():
    text = 'आप backend project के बारे में बताइए।'
    assert validate_assistant_script(text, 'hinglish') is True


def test_validate_rejects_roman_hindi_hinglish():
    text = 'Shuru karne se pehle, screen share on rakhein.'
    assert validate_assistant_script(text, 'hinglish') is False


def test_validate_english_only():
    assert validate_assistant_script('Please tell me about your project.', 'en') is True
    assert validate_assistant_script('आप बताइए।', 'en') is False


def test_normalize_mixed_script_preserves_devanagari():
    text = 'आप React use करते हैं'
    result = normalize_mixed_script(text)
    assert 'आप' in result
    assert 'React' in result
    assert 'करते' in result


def test_prepare_text_fast_path_llm_compliant():
    text = 'आप backend project के बारे में बताइए।'
    result = prepare_text_for_tts(
        text,
        reply_script='hinglish',
        llm_compliant=True,
    )
    assert 'आप' in result
    assert 'backend' in result
    assert validate_assistant_script(result, 'hinglish')


def test_strict_hints_non_empty():
    assert 'Devanagari' in llm_language_hint_strict('hinglish')
    assert 'mandatory' in system_script_rules('hi').lower()
