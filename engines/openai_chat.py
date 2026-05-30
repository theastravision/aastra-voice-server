"""OpenAI chat completions with compatible token limit parameters."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_chat_completion(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, str]],
    max_output_tokens: int = 512,
    temperature: float = 0.7,
) -> Any:
    """Use max_completion_tokens (new models) with fallback to max_tokens (legacy)."""
    base: dict[str, Any] = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
    }
    try:
        return client.chat.completions.create(
            **base,
            max_completion_tokens=max_output_tokens,
        )
    except Exception as exc:
        err = str(exc).lower()
        if 'max_completion_tokens' in err and 'unsupported' in err:
            logger.debug('Falling back to max_tokens for model %s', model)
            return client.chat.completions.create(
                **base,
                max_tokens=max_output_tokens,
            )
        if 'max_tokens' in err and 'unsupported' in err:
            logger.debug('Falling back to max_completion_tokens for model %s', model)
            return client.chat.completions.create(
                **base,
                max_completion_tokens=max_output_tokens,
            )
        raise
