"""Tests for session state machine greeting guard."""

from __future__ import annotations

import asyncio

import pytest

from streaming.session_state import SessionPhase, SessionStateMachine


@pytest.mark.asyncio
async def test_greeting_runs_once():
    state = SessionStateMachine()
    assert await state.try_greet() is True
    assert state.is_greeted is True
    assert await state.try_greet() is False


@pytest.mark.asyncio
async def test_stt_blocked_while_locked():
    state = SessionStateMachine()
    await state.try_greet()
    assert await state.accept_pcm_for_stt() is False
    await state.begin_listening()
    assert await state.accept_pcm_for_stt() is True


@pytest.mark.asyncio
async def test_begin_listening_after_greeting():
    state = SessionStateMachine()
    await state.try_greet()
    assert state.phase == SessionPhase.GREETING
    await state.begin_listening()
    assert state.phase == SessionPhase.LISTENING
