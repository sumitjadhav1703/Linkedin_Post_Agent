"""LLM factories and retry wrapper."""

import logging
import time
from typing import Any

from langchain_groq import ChatGroq

from app import config

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """A provider call that failed after all retries."""


def make_writer_llm() -> ChatGroq:
    config.require_groq_key()

    return ChatGroq(
        model=config.WRITER_MODEL,
        temperature=config.WRITER_TEMPERATURE,
        max_retries=config.LLM_MAX_RETRIES,
    )


def make_reviewer_llm() -> ChatGroq:
    config.require_groq_key()

    return ChatGroq(
        model=config.REVIEWER_MODEL,
        temperature=config.REVIEWER_TEMPERATURE,
        max_retries=config.LLM_MAX_RETRIES,
    )


def invoke_with_retry(runnable: Any, payload: Any, *, what: str) -> Any:
    """Invoke a runnable with retries only for transient failures."""

    last_error: Exception | None = None

    for attempt in range(config.LLM_MAX_RETRIES + 1):
        try:
            return runnable.invoke(payload)

        except Exception as exc:  # noqa: BLE001
            last_error = exc
            message = str(exc)

            # Permanent request/configuration errors should not be retried.
            if "400 Bad Request" in message or "tool_use_failed" in message:
                logger.error("%s failed with a non-retryable error: %s", what, exc)
                raise LLMError(f"{what} call failed: {exc}") from exc

            if attempt < config.LLM_MAX_RETRIES:
                delay = config.LLM_RETRY_BASE_DELAY * (2 ** attempt)

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
