"""LLM factories and a retry wrapper.

Every LLM call in the graphs goes through invoke_with_retry so a provider
hiccup surfaces as a typed LLMError the nodes can catch, rather than an
exception that kills the process mid-demo.
"""

import logging
import time
from typing import Any

from langchain_mistralai import ChatMistralAI

from app import config

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """A provider call that failed after all retries."""


def make_writer_llm() -> ChatMistralAI:
    config.require_mistral_key()
    return ChatMistralAI(
        model=config.WRITER_MODEL,
        temperature=config.WRITER_TEMPERATURE,
    )


def make_reviewer_llm() -> ChatMistralAI:
    config.require_mistral_key()
    return ChatMistralAI(
        model=config.REVIEWER_MODEL,
        temperature=config.REVIEWER_TEMPERATURE,
    )


def invoke_with_retry(runnable: Any, payload: Any, *, what: str) -> Any:
    """Invoke a runnable, retrying transient failures with backoff.

    `what` is a short human label used in logs and in the error surfaced to the
    frontend, e.g. "writer" or "reviewer".
    """
    last_error: Exception | None = None

    for attempt in range(config.LLM_MAX_RETRIES + 1):
        try:
            return runnable.invoke(payload)
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
            last_error = exc
            if attempt < config.LLM_MAX_RETRIES:
                delay = config.LLM_RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "%s call failed (attempt %d/%d): %s — retrying in %.1fs",
                    what,
                    attempt + 1,
                    config.LLM_MAX_RETRIES + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "%s call failed after %d attempts: %s",
                    what,
                    config.LLM_MAX_RETRIES + 1,
                    exc,
                    exc_info=True,
                )

    raise LLMError(f"{what} call failed: {last_error}") from last_error
