"""Tests for svara-TTS text preparation."""

from engines.tts_svara_pipeline import prepare_text_for_svara


def test_svara_skips_phonetic_hyphens():
    text = 'Phir Aashish ne decide kiya, technology engineer banega.'
    result = prepare_text_for_svara(text, reply_script='hinglish')
    assert 'dee-sa-eed' not in result
    assert 'tek-no-lo-jee' not in result
    assert 'decide' in result or 'डिस' in result or 'decide' in result.lower()


def test_svara_adds_pauses_for_hinglish():
    text = 'Phir Aashish ne decide kiya, ki woh engineer banega.'
    result = prepare_text_for_svara(text, reply_script='hinglish')
    assert '...' in result


def test_svara_hindi_devanagari():
    text = 'Namaste, main aapka interview loongi.'
    result = prepare_text_for_svara(text, reply_script='hi')
    assert result
    assert 'dee-sa-eed' not in result
