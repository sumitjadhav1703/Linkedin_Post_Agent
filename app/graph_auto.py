"""Autonomous graph: an LLM reviewer gates every draft.

Identical to `graph_hitl` except for the review node — no human, so no
suspension, so no checkpointer needed. The loop runs start to finish in one
call.
"""

import logging

from langgraph.graph import END, StateGraph

from app.reviewer import reviewer_node
from app.state import PostState
from app.writer import (
    WRITER_ENTRY_NODE,
    WRITER_EXIT_NODE,
    add_writer_chain,
    route_after_review,
)

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    graph = StateGraph(PostState)
    add_writer_chain(graph)

    graph.add_node("reviewer", reviewer_node)
    graph.add_edge(WRITER_EXIT_NODE, "reviewer")
    graph.add_conditional_edges(
        "reviewer",
        route_after_review,
        {WRITER_ENTRY_NODE: WRITER_ENTRY_NODE, END: END},
    )
    return graph


# No checkpointer: nothing ever pauses, so there is no state to resume from.
app_auto = build_graph().compile()
