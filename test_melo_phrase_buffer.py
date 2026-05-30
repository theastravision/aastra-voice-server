"""Tests for MeloTTS Hindi phrase buffer."""

from engines.melo_phrase_buffer import HindiPhraseBuffer


def _push_tokens(buf: HindiPhraseBuffer, text: str) -> list[str]:
    chunks: list[str] = []
    for token in text:
        chunks.extend(buf.push(token))
    return chunks


def test_devanagari_danda_flush():
    buf = HindiPhraseBuffer()
    chunks = _push_tokens(buf, 'नमस्ते, आप कैसे हैं।')
    assert len(chunks) == 1
    assert chunks[0].endswith('।') or 'नमस्ते' in chunks[0]


def test_hinglish_no_flush_on_comma():
    buf = HindiPhraseBuffer()
    partial = 'Hum sakshatkar ka aarambh kar sakte hain, jab bhi aap taiyar hon.'
    chunks = _push_tokens(buf, partial)
    assert len(chunks) == 1
    assert 'aarambh' in chunks[0]
    assert chunks[0].endswith('.')


def test_commas_mid_sentence_do_not_split():
    buf = HindiPhraseBuffer()
    text = 'Pehle, screen share on rakhein, phir shuru karte hain.'
    chunks = _push_tokens(buf, text)
    assert len(chunks) == 1
    assert 'Pehle' in chunks[0]
    assert 'karte hain' in chunks[0]


def test_markdown_stripped():
    buf = HindiPhraseBuffer()
    chunks = _push_tokens(buf, '**bold** text yahan hai.')
    assert len(chunks) == 1
    assert '**' not in chunks[0]
    assert 'bold text yahan hai.' in chunks[0]


def test_flush_remainder():
    buf = HindiPhraseBuffer()
    buf.push('Kuch bacha hua text')
    remainder = buf.flush()
    assert remainder == 'Kuch bacha hua text'
    assert buf.flush() == ''


def test_exclamation_boundary():
    buf = HindiPhraseBuffer()
    chunks = _push_tokens(buf, 'Taiyar ho! Chalo shuru karte hain.')
    assert len(chunks) == 2
    assert chunks[0].endswith('!')
    assert 'Chalo' in chunks[1]
