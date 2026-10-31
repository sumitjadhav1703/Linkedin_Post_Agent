"""Shared configuration: model IDs, limits, env-key checks, logging setup.

Loads local .env configuration at runtime. Key checks report presence only;
secret values are never printed. Tests disable dotenv loading.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

# Both graphs share the writer. These model IDs refer to NVIDIA hosted endpoints.
WRITER_MODEL = "meta/llama-3.3-70b-instruct"

WRITER_TEMPERATURE = 0.7

REVIEWER_MODEL = WRITER_MODEL

REVIEWER_TEMPERATURE = 0.2

MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "2"))
if not 1 <= MAX_ATTEMPTS <= 5:
    raise ValueError("MAX_ATTEMPTS must be between 1 and 5.")

LLM_MAX_RETRIES = 1
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
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,https://linkedin-post-agent-two.vercel.app"
    ).split(",")
    if origin.strip()
]

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_KEY_NAME = "NVIDIA_API_KEY"
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


def require_nvidia_key() -> None:
    if not has_key(NVIDIA_KEY_NAME):
        raise RuntimeError(
            f"{NVIDIA_KEY_NAME} is not set. Add it to your .env file or export it "
            "before starting the app."
        )
