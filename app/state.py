"""The state schema shared by both graphs.

Both the human-in-the-loop and autonomous graphs use this exact type. Sharing
it is what makes the two runs comparable: same inputs, same accumulated
history, same stopping conditions.
"""

from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages


class PostState(TypedDict):
    """State carried through both review loops."""

    topic: str

    # Load-bearing, not decorative: this carries the writer's own drafts, the
    # instruction messages, and the ToolMessage results from web search back
    # into the next writer call.
    messages: Annotated[list, add_messages]

    draft: str
    review_feedback: str
    is_approved: bool
    attempt: int

    # Set by any node whose LLM or tool call failed. The router sends states
    # carrying an error straight to END so the API can surface it rather than
    # the process dying.
    error: Optional[str]

    enable_search: bool


def initial_state(topic: str, enable_search: bool = False) -> PostState:
    """Build a fresh state. Used by the API and both CLI entry points."""
    return {
        "topic": topic,
        "messages": [],
        "draft": "",
        "review_feedback": "",
        "is_approved": False,
        "attempt": 0,
        "error": None,
        "enable_search": enable_search,
    }
