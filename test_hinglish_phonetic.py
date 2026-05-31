"""Tests for dynamic Hinglish phonetic spacing and STT denormalization."""

from engines.hinglish_phonetic import (
    HinglishPhoneticEngine,
    apply_phonetic_hyphens,
    denormalize_phonetic_text,
    denormalize_phonetic_word,
    get_phonetic_engine,
)
from engines.tts_text_pipeline import prepare_text_for_tts

AASHISH_STORY = (
    'Phir Aashish ne decide kiya, ki woh bada hokar engineer banega. '
    'Aur aisi technology banayega, jo gaon, shehar aur desh ke logon ki zindagi aasaan bana sake.'
)

MIXED_TECH = (
    'Phir Aashish ne decide kiya ki woh software engineer banega, '
    'configuration management pipeline architecture optimize karne ke liye.'
)


def test_glossary_technology_uses_spaces_not_hyphens():
    result = apply_phonetic_hyphens('technology', reply_script='hinglish')
    assert result == 'tek no lo jee'
    assert '-' not in result


def test_glossary_engineer_preserves_case():
    assert apply_phonetic_hyphens('Engineer', reply_script='hinglish') == 'In jin eer'


def test_glossary_zindagi():
    assert apply_phonetic_hyphens('zindagi', reply_script='hinglish') == 'zin da gi'


def test_dynamic_unseen_word_gets_syllable_spaces():
    result = apply_phonetic_hyphens('configuration', reply_script='hinglish')
    assert ' ' in result
    assert '-' not in result
    assert result != 'configuration'


def test_dynamic_hindi_roman_banega():
    result = apply_phonetic_hyphens('banega', reply_script='hinglish')
    assert result == 'ba ne ga'


def test_skips_short_particles():
    engine = get_phonetic_engine()
    assert engine.transform_word('ki') == 'ki'
    assert engine.transform_word('ne') == 'ne'


def test_skips_interview_names():
    engine = get_phonetic_engine()
    assert engine.transform_word('Aashish') == 'Aashish'


def test_english_session_unchanged():
    text = 'Tell me about your technology experience.'
    assert apply_phonetic_hyphens(text, reply_script='en') == text


def test_legacy_hyphen_input_converted_to_spaces():
    assert apply_phonetic_hyphens('tek-no-lo-jee', reply_script='hinglish') == 'tek no lo jee'


def test_mixed_sentence_dynamic_and_glossary():
    result = apply_phonetic_hyphens(MIXED_TECH, reply_script='hinglish')
    assert 'dee sa eed' in result
    assert 'soft ware' in result
    assert 'in jin eer' in result
    assert '-' not in result


def test_stt_denorm_glossary_word():
    assert denormalize_phonetic_word('tek-no-lo-jee') == 'technology'
    assert denormalize_phonetic_text('tek no lo jee stack', reply_script='hinglish') == 'technology stack'


def test_stt_denorm_dynamic_word():
    assert denormalize_phonetic_word('ba-ne-ga') == 'banega'


def test_stt_denorm_sentence_roundtrip():
    phonetic = apply_phonetic_hyphens(MIXED_TECH, reply_script='hinglish')
    restored = denormalize_phonetic_text(phonetic, reply_script='hinglish')
    assert 'software engineer' in restored.lower()
    assert 'con fi gu ra shun' in restored.lower()
    assert 'management' in restored.lower() or 'ma na ge ment' in restored.lower()
    assert 'dee sa eed' not in restored.lower()


def test_stt_denorm_skipped_for_english():
    text = 'tek no lo jee stack'
    assert denormalize_phonetic_text(text, reply_script='en') == text


def test_full_story_pipeline():
    result = prepare_text_for_tts(AASHISH_STORY, reply_script='hinglish')
    assert 'tek no lo jee' in result
    assert 'in jin eer' in result
    assert 'dee sa eed' in result
    assert 'zin da gi' in result
    assert 'aa saan' in result
    assert '-' not in result
    assert result.count('...') >= 4


def test_engine_class_process_sentence():
    engine = HinglishPhoneticEngine()
    out = engine.process_sentence('optimize karne')
    assert 'op ti mi ze' in out or 'optimize' in out
    assert 'kar ne' in out or 'karne' in out
    assert '-' not in out
