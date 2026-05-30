"""Unit tests for Hinglish romanization normalizer."""

from engines.hinglish_normalize import normalize_hinglish


def test_acha_to_achha():
    assert normalize_hinglish('Acha, samajh gaya') == 'Achha, samajh gaya'


def test_samjha_to_samajh():
    assert 'samajh' in normalize_hinglish('main samjha nahi')


def test_kam_to_kaam():
    assert normalize_hinglish('yeh kam important hai') == 'yeh kaam important hai'


def test_preserves_devanagari():
    text = 'नमस्ते acha lagta hai'
    result = normalize_hinglish(text)
    assert 'नमस्ते' in result
    assert 'achha' in result


def test_thik_to_theek():
    assert normalize_hinglish('thik hai') == 'theek hai'


def test_collapse_repeated_chars():
    assert normalize_hinglish('samajhhh') == 'samajh'


def test_prepare_text_for_f5_devanagari_mode():
    from engines.tts_text_pipeline import prepare_text_for_f5_tts

    result = prepare_text_for_f5_tts(
        'Shuru karne se pehle',
        reply_script='hinglish',
    )
    assert any('\u0900' <= ch <= '\u097f' for ch in result)


def test_to_devanagari_mixed_keeps_english():
    from engines.tts_text_pipeline import to_devanagari_mixed

    result = to_devanagari_mixed('React use karta hoon', reply_script='hinglish')
    assert 'React' in result
    assert any('\u0900' <= ch <= '\u097f' for ch in result)


def test_preprocess_debug_tokens():
    from engines.tts_text_pipeline import preprocess_debug

    data = preprocess_debug('Shuru karne se pehle', reply_script='hinglish')
    assert data['original']
    assert data['devanagari']
    assert data['tokens']


def test_phrase_buffer_first_chunk():
    from llm_worker import PhraseBuffer

    buf = PhraseBuffer(first_min_words=3, next_min_words=5)
    chunks = []
    for token in 'Hello there friend, how are you doing today?'.split(' '):
        chunks.extend(buf.push(token + ' '))
    assert chunks
    assert len(chunks[0].split()) <= 4
