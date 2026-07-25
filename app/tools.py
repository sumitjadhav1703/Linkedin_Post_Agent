"""Web search tool, shared by both graphs.

Degrades gracefully: with no TAVILY_API_KEY the tool list is empty, the writer
binds no tools, and posts are written unaugmented. A missing optional key
should never take the demo down.
"""

import logging
from functools import lru_cache

from app import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_tools() -> list:
    """Return the tool list, or [] when search is unavailable."""
    if not config.has_key(config.TAVILY_KEY_NAME):
        logger.warning(
            "%s not set — web search disabled, writer will run unaugmented.",
            config.TAVILY_KEY_NAME,
        )
        return []

    try:
        from langchain_tavily import TavilySearch
    except ImportError:
        logger.warning("langchain-tavily is not installed — web search disabled.")
        return []

    try:
        return [TavilySearch(max_results=config.TAVILY_MAX_RESULTS)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not construct the Tavily tool (%s) — search disabled.", exc)
        return []


def search_available() -> bool:
    return bool(get_tools())
