"""NVIDIA model factories and one bounded retry layer."""
import logging
import re
import time
from typing import Any

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from requests.exceptions import ConnectionError, Timeout

from app import config

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Safe application error; never includes a raw provider response."""
    def __init__(self, message, *, status_code=None, allow_fallback=False):
        super().__init__(message)
        self.status_code = status_code
        self.allow_fallback = allow_fallback


def make_writer_llm() -> ChatNVIDIA:
    config.require_nvidia_key()
    return ChatNVIDIA(model=config.WRITER_MODEL, base_url=config.NVIDIA_BASE_URL,
                      temperature=config.WRITER_TEMPERATURE, max_completion_tokens=1024,
                      timeout=45, usage_telemetry_enabled=False,
                      model_kwargs={"chat_template_kwargs": {"enable_thinking": False}, "tool_choice": "none"})


def make_reviewer_llm() -> ChatNVIDIA:
    config.require_nvidia_key()
    return ChatNVIDIA(model=config.REVIEWER_MODEL, base_url=config.NVIDIA_BASE_URL,
                      temperature=config.REVIEWER_TEMPERATURE, max_completion_tokens=512,
                      timeout=45, usage_telemetry_enabled=False,
                      model_kwargs={"chat_template_kwargs": {"enable_thinking": False}, "tool_choice": "none"})


def invoke_with_retry(runnable: Any, payload: Any, *, what: str) -> Any:
    """Retry only network/5xx failures once. Quota and auth errors stop immediately."""
    for attempt in range(config.LLM_MAX_RETRIES + 1):
        try:
            return runnable.invoke(payload)
        except LLMError:
            raise
        except Exception as exc:
            status = getattr(exc, 'status_code', None)
            response = getattr(exc, 'response', None)
            if status is None and response is not None:
                status = response.status_code
            # ChatNVIDIA 1.5 formats HTTP errors as generic Exception('[429] ...').
            if status is None:
                match = re.match(r'^\[(\d{3})\]', str(exc))
                status = int(match.group(1)) if match else None
            transient = isinstance(exc, (ConnectionError, Timeout, TimeoutError)) or (
                isinstance(status, int) and 500 <= status <= 599)
            logger.warning('%s failed: status=%s type=%s attempt=%s',
                           what, status, type(exc).__name__, attempt + 1)
            if transient and attempt < config.LLM_MAX_RETRIES:
                time.sleep(config.LLM_RETRY_BASE_DELAY * (2 ** attempt))
                continue
            if status == 429:
                message = 'NVIDIA usage limit reached. Wait before retrying and check your API-catalog quota. Your existing draft remains available.'
            elif status in (401, 403):
                message = 'NVIDIA rejected API access. Check NVIDIA_API_KEY and model access on the backend.'
            elif status in (404, 410):
                message = 'The configured NVIDIA model is unavailable or retired. Update the backend model before retrying.'
            elif transient:
                message = 'NVIDIA did not respond successfully. Wait briefly before retrying.'
            else:
                message = f'The {what} request could not complete. Check backend configuration and model support.'
            schema_error = (status in (400, 422) and any(
                term in str(exc).lower() for term in ('schema', 'tool', 'structured', 'response_format')))
            raise LLMError(message, status_code=status,
                           allow_fallback=schema_error or isinstance(exc, (ValueError, NotImplementedError))) from exc
