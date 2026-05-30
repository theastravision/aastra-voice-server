"""Pre-cached interjection filler audio for low-latency backchannels."""

from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

ReplyScript = Literal['en', 'hi', 'hinglish']

# (text, primary script tag for pool selection)
_FILLER_CLIPS: tuple[tuple[str, ReplyScript], ...] = (
    ('Hmm...', 'en'),
    ("Let's see...", 'en'),
    ('Okay...', 'en'),
    ('Achha...', 'hi'),
    ('Sahi kaha...', 'hi'),
    ('Theek hai...', 'hi'),
)


@dataclass(frozen=True)
class CachedInterjection:
    text: str
    pcm_s16le: bytes
    sample_rate: int
    reply_script: ReplyScript


_cache: list[CachedInterjection] = []
_cache_lock = threading.Lock()
_ready = False


def warmup_interjections() -> None:
    """Pre-synthesize filler clips at startup."""
    global _ready
    with _cache_lock:
        if _ready:
            return
        from engines.f5_tts_engine import get_manager

        mgr = get_manager()
        clips: list[CachedInterjection] = []
        for text, script in _FILLER_CLIPS:
            try:
                mgr.reset_stream_state()
                pcm_parts: list[bytes] = []
                sr = mgr.sample_rate
                for pcm, rate in mgr.synthesize_stream_sync(text, reply_script=script):
                    pcm_parts.append(pcm)
                    sr = rate
                if pcm_parts:
                    clips.append(
                        CachedInterjection(
                            text=text,
                            pcm_s16le=b''.join(pcm_parts),
                            sample_rate=sr,
                            reply_script=script,
                        )
                    )
            except Exception:
                logger.exception('Failed to cache interjection: %s', text)
        _cache.clear()
        _cache.extend(clips)
        _ready = True
        logger.info('Cached %d interjection clips', len(_cache))


def pick_interjection(reply_script: ReplyScript = 'en') -> CachedInterjection | None:
    """Pick a language-matched filler. Disabled for English-only sessions."""
    if reply_script == 'en':
        return None
    with _cache_lock:
        if reply_script == 'hi':
            pool = [c for c in _cache if c.reply_script == 'hi']
        elif reply_script == 'hinglish':
            pool = list(_cache)
        else:
            pool = list(_cache)
        if not pool:
            return None
        return random.choice(pool)


def interjections_ready() -> bool:
    with _cache_lock:
        return bool(_cache)
