"""WebSocket message types for /ws/voice streaming."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any


class WsType(str, Enum):
    CONFIG = 'config'
    END_UTTERANCE = 'end_utterance'
    BARGE_IN = 'barge_in'
    LISTEN_READY = 'listen_ready'
    PING = 'ping'

    STT_PARTIAL = 'stt_partial'
    STT_FINAL = 'stt_final'
    ASSISTANT_DELTA = 'assistant_delta'
    ASSISTANT_TEXT = 'assistant_text'
    AUDIO_CONFIG = 'audio_config'
    TURN_START = 'turn_start'
    TURN_END = 'turn_end'
    ERROR = 'error'
    PONG = 'pong'


def json_event(event_type: str | WsType, **fields: Any) -> str:
    payload: dict[str, Any] = {'type': event_type.value if isinstance(event_type, WsType) else event_type}
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=False)


def parse_client_message(raw: str) -> dict[str, Any]:
    return json.loads(raw)
