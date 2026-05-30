"""Tests for Hinglish vocab loader."""

from engines.hinglish_vocab import (
    build_whisper_vocab_prompt,
    clean_utterance,
    hinglish_particles,
    is_clean_lexicon_token,
    iter_conversation_utterances,
    iter_lexicon_words,
    vocab_stats,
)


def test_rejects_noisy_lexicon_tokens():
    assert not is_clean_lexicon_token('720p')
    assert not is_clean_lexicon_token('100rs')
    assert not is_clean_lexicon_token('www.foo.com')
    assert is_clean_lexicon_token('yaar')


def test_clean_utterance_rejects_phantom():
    assert clean_utterance('thank you') is None
    assert clean_utterance('Terms. Terms. Terms.') is None


def test_conversation_utterances_non_empty():
    utterances = iter_conversation_utterances()
    assert len(utterances) >= 100
    assert all(len(u) >= 8 for u in utterances[:20])


def test_lexicon_words_filtered():
    words = iter_lexicon_words(min_freq=1)
    assert len(words) >= 500
    assert all(is_clean_lexicon_token(w) for w, _ in words[:50])


def test_particles_include_builtins():
    particles = hinglish_particles()
    assert 'yaar' in particles
    assert 'kripya' in particles


def test_whisper_prompt_within_limit():
    prompt = build_whisper_vocab_prompt(max_chars=400)
    assert len(prompt) <= 400
    assert 'Hinglish' in prompt


def test_vocab_stats():
    stats = vocab_stats()
    assert stats['lexicon_rows'] > 0
    assert stats['clean_utterances'] > 0
    assert stats['particle_count'] > 0
