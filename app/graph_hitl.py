"""Human-in-the-loop graph: a person gates every draft.

Identical to `graph_auto` except for the review node — here the graph suspends
with `interrupt()` and waits for a real human verdict, which is why this one
needs a checkpointer and the autonomous one does not.
"""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.state import PostState
from app.writer import (
    WRITER_ENTRY_NODE,
    WRITER_EXIT_NODE,
    add_writer_chain,
    route_after_review,
)

logger = logging.getLogger(__name__)

REVIEW_INSTRUCTION = (
    "Type 'approved' to accept, or type your feedback to request a rewrite."
)

APPROVAL_WORDS = {"approved", "approve", "yes", "ok", "okay", "good", "lgtm", "ship it"}


def human_review_node(state: PostState) -> dict:
    """Suspend the graph and wait for a human verdict.

    Everything before `interrupt()` re-executes when the graph resumes, so this
    node deliberately does no work and has no side effects before that call.
    """
    # Never ask a human to approve the output of a failed run. Returning
    # without interrupting lets route_after_review send the error to END.
    if state.get("error"):
        return {}

    human_response = interrupt(
        {
            "draft": state["draft"],
            "attempt": state["attempt"],
            "instruction": REVIEW_INSTRUCTION,
        }
    )

    response = str(human_response).strip()
    approved = response.lower() in APPROVAL_WORDS

    logger.info(
        "Human verdict on attempt %d: %s",
        state["attempt"],
        "APPROVED" if approved else "REVISION REQUESTED",
    )

    return {
        "is_approved": approved,
        "review_feedback": "Approved by human." if approved else response,
    }


def build_graph() -> StateGraph:
    graph = StateGraph(PostState)
    add_writer_chain(graph)

    graph.add_node("human_review", human_review_node)
    graph.add_edge(WRITER_EXIT_NODE, "human_review")
    graph.add_conditional_edges(
        "human_review",
        route_after_review,
        {WRITER_ENTRY_NODE: WRITER_ENTRY_NODE, END: END},
    )
    return graph


# A checkpointer is mandatory here: interrupt() persists the paused graph and
# resume reads it back by thread_id. MemorySaver keeps it in process memory,
# which is fine for a single-worker demo — see PLAN.md for what that implies
# for hosting.
checkpointer = MemorySaver()
app_hitl = build_graph().compile(checkpointer=checkpointer)
