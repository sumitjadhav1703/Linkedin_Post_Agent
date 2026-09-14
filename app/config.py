"""Shared configuration: model IDs, limits, env-key checks, logging setup.

Never reads or prints .env contents. Key checks go through os.environ key
names only and report presence as a boolean.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

# Both graphs use the same writer so the only difference between them is the
# review mechanism. "mistral-small-latest" is the current alias; the bare
# "mistral-small" alias is deprecated and "mistral-7b-instruct" is retired.
WRITER_MODEL = os.environ.get(
    "WRITER_MODEL",
    "openai/gpt-oss-20b",
)

WRITER_TEMPERATURE = 0.7

REVIEWER_MODEL = os.environ.get(
    "REVIEWER_MODEL",
    "openai/gpt-oss-20b",
)

REVIEWER_TEMPERATURE = 0.2

MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))

LLM_MAX_RETRIES = 2
LLM_RETRY_BASE_DELAY = 1.0

TAVILY_MAX_RESULTS = 3

# MAX_ATTEMPTS rounds of (prepare, write, maybe search, extract, review) plus
# slack. LangGraph's default of 25 is tight once search loops are in play.
GRAPH_RECURSION_LIMIT = 60

# In-process stores are capped so a long-lived demo process cannot grow without
# bound. Oldest entries are evicted first.
MAX_TRACKED_SESSIONS = 100
MAX_TRACKED_JOBS = 100

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    if origin.strip()
]

MISTRAL_KEY_NAME = "MISTRAL_API_KEY"
TAVILY_KEY_NAME = "TAVILY_API_KEY"

_LOGGING_CONFIGURED = False


def configure_logging() -> None:
    """Set up root logging once. Level comes from LOG_LEVEL, default INFO."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    _LOGGING_CONFIGURED = True


def has_key(name: str) -> bool:
    """Report whether an API key is set, without touching its value."""
    return bool(os.environ.get(name))


def require_mistral_key() -> None:
    """Fail fast with an actionable message rather than deep inside a call."""
    if not has_key(MISTRAL_KEY_NAME):
        raise RuntimeError(
            f"{MISTRAL_KEY_NAME} is not set. Add it to your .env file or export it "
            "before starting the app."
        )
