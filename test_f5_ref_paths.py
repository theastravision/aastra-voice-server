"""Tests for language-specific F5 reference env resolution."""

from __future__ import annotations

from config import (
    F5_REF_AUDIO_EN,
    F5_REF_AUDIO_HINGLISH,
    F5_REF_TEXT_EN,
    F5_REF_TEXT_HINGLISH,
    resolve_f5_ref_paths,
)


def test_resolve_f5_ref_english():
    audio, text = resolve_f5_ref_paths(reply_script='en', voice_id='astra')
    assert audio == F5_REF_AUDIO_EN
    assert text == F5_REF_TEXT_EN


def test_resolve_f5_ref_hinglish_by_script():
    audio, text = resolve_f5_ref_paths(reply_script='hinglish')
    assert audio == F5_REF_AUDIO_HINGLISH
    assert text == F5_REF_TEXT_HINGLISH


def test_resolve_f5_ref_hinglish_by_voice_id():
    audio, text = resolve_f5_ref_paths(voice_id='astra_hinglish', reply_script='en')
    assert audio == F5_REF_AUDIO_HINGLISH
    assert text == F5_REF_TEXT_HINGLISH
