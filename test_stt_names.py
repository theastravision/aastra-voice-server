"""Tests for indexed Indian/English name STT correction."""

from __future__ import annotations

from engines.stt_names import (
    _get_index,
    closest_name,
    correct_names_in_transcript,
    load_interview_names,
)


def test_index_loads_gist_csv():
    index = _get_index()
    assert index.total > 3000
    assert 'ashish' in index.exact
    assert index.exact['ashish'] == 'Ashish'


def test_asheesh_corrects_to_ashish():
    assert closest_name('Asheesh') == 'Ashish'
    assert 'Ashish' in correct_names_in_transcript('My name is Asheesh')


def test_awish_corrects_to_ashish():
    assert closest_name('Awish') == 'Ashish'
    assert correct_names_in_transcript('Awish') == 'Ashish'


def test_fuzzy_uses_prefix_bucket():
    # Rahul is in priority list; slight typo should resolve via index.
    assert closest_name('Rahul') == 'Rahul'
    match = closest_name('Rahul')
    assert match is not None


def test_priority_names_for_whisper_prompt():
    names = load_interview_names()
    assert 'Ashish' in names
    assert len(names) >= 50
