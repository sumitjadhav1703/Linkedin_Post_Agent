"""The writer chain — shared verbatim by both graphs.

This module owns everything up to the point of review: attempt bookkeeping,
prompt construction, the LLM call, the search tool loop, and draft extraction.
Both graph modules import `add_writer_chain` and attach their own review node
to `WRITER_EXIT_NODE`, so the two pipelines cannot drift apart. The review
mechanism is the deliberate — and only — difference between them.
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app import config, prompts, tools
from app.llm import LLMError, invoke_with_retry, make_writer_llm
from app.state import PostState

logger = logging.getLogger(__name__)

# The node a review node should attach itself after.
WRITER_EXIT_NODE = "extract_draft"
# The node a review node routes back to in order to start another attempt.
WRITER_ENTRY_NODE = "prepare_attempt"

# Cap on consecutive search rounds within a single attempt, so a model that
# keeps deciding to search can never stall a live demo.
MAX_TOOL_ROUNDS = 2

_writer_llm = None
_writer_llm_with_tools = None


def _get_writer_llm(with_tools: bool):
    """Lazily build the writer LLM so importing this module needs no API key."""
    global _writer_llm, _writer_llm_with_tools

    if _writer_llm is None:
        _writer_llm = make_writer_llm()

    if not with_tools:
        return _writer_llm

    if _writer_llm_with_tools is None:
    _writer_llm_with_tools = _writer_llm.bind_tools(
        tools.get_tools(),
        tool_choice="auto",
    )
    return _writer_llm_with_tools


def _use_tools(state: PostState) -> bool:
    return bool(state.get("enable_search")) and tools.search_available()


def _as_text(content) -> str:
    """Normalise message content, which may arrive as a list of blocks."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()
    return str(content).strip()


def prepare_attempt_node(state: PostState) -> dict:
    """Increment the attempt counter and append the instruction message.

    Pure Python, no LLM call. Owning prompt construction here is what keeps the
    two graphs phrasing their revision instruction identically.
    """
    attempt = state.get("attempt", 0) + 1
    topic = state["topic"]
    feedback = state.get("review_feedback", "")

    if attempt == 1:
        instruction = prompts.first_attempt_instruction(topic)
    else:
        instruction = prompts.revision_instruction(topic, feedback)

    logger.info("Starting attempt %d/%d", attempt, config.MAX_ATTEMPTS)

    return {
        "attempt": attempt,
        "messages": [HumanMessage(content=instruction)],
    }


def writer_node(state: PostState) -> dict:
    """Call the writer on the full accumulated history.

    Passing `state["messages"]` rather than a freshly rebuilt pair is what lets
    the writer actually see its previous drafts, the reviewer's feedback, and
    any search results it asked for.
    """
    with_tools = _use_tools(state)

    try:
        llm = _get_writer_llm(with_tools)
        response = invoke_with_retry(
            llm,
            [SystemMessage(content=prompts.WRITER_SYSTEM_PROMPT)] + state["messages"],
            what="writer",
        )
    except (LLMError, RuntimeError) as exc:
        logger.error("Writer node failed: %s", exc)
        return {"error": str(exc)}

    if getattr(response, "tool_calls", None):
        logger.info("Writer requested %d search call(s)", len(response.tool_calls))

    return {"messages": [response]}


def extract_draft_node(state: PostState) -> dict:
    """Pull the finished post text off the last AI message."""
    if state.get("error"):
        return {}

    last = state["messages"][-1]

    # If the writer failed, the last message is still the instruction we fed it.
    # Extracting that would hand the review node the prompt as if it were a
    # draft, which reads as a plausible post and hides the failure.
    if not isinstance(last, AIMessage):
        logger.error("Expected an AI message to extract, got %s", type(last).__name__)
        return {"error": "The writer did not produce a response."}

    draft = _as_text(getattr(last, "content", ""))

    if not draft:
        logger.error("Writer produced an empty draft")
        return {"error": "The writer produced an empty draft."}

    logger.info("Draft ready for attempt %d (%d chars)", state["attempt"], len(draft))
    logger.debug("Draft attempt %d:\n%s", state["attempt"], draft)

    return {"draft": draft}


def route_after_writer(state: PostState) -> str:
    """Send tool calls to the tool node, finished prose to draft extraction."""
    # Straight to END, not on to extraction and review. A failed write has no
    # draft, and letting it reach the review node means a human gets asked to
    # approve nothing, or the reviewer grades an empty string.
    if state.get("error"):
        return END

    last = state["messages"][-1]
    if not getattr(last, "tool_calls", None):
        return WRITER_EXIT_NODE

    tool_rounds = sum(
        1
        for message in state["messages"]
        if isinstance(message, AIMessage) and getattr(message, "tool_calls", None)
    )
    if tool_rounds > MAX_TOOL_ROUNDS:
        logger.warning(
            "Hit the %d-round search cap — writing with the context gathered so far.",
            MAX_TOOL_ROUNDS,
        )
        return WRITER_EXIT_NODE

    return "tools"


def route_after_review(state: PostState) -> str:
    """Decide whether to loop for another attempt or stop.

    Shared by both graphs, so "when do we give up" is identical whether the
    reviewer is a human or an LLM.
    """
    if state.get("error"):
        logger.error("Ending early: %s", state["error"])
        return END

    if state.get("is_approved"):
        logger.info("Approved on attempt %d — ending.", state["attempt"])
        return END

    if state["attempt"] >= config.MAX_ATTEMPTS:
        logger.info(
            "Hit the %d-attempt cap — ending with the last draft.", config.MAX_ATTEMPTS
        )
        return END

    logger.info("Rejected — looping back for attempt %d.", state["attempt"] + 1)
    return WRITER_ENTRY_NODE


def stop_reason(state: PostState) -> str:
    """Why the loop ended. Lets the frontend distinguish the two endings."""
    if state.get("error"):
        return "error"
    if state.get("is_approved"):
        return "approved"
    return "max_attempts"


def add_writer_chain(graph: StateGraph) -> None:
    """Attach the shared writer pipeline to a graph.

    Wires START -> prepare_attempt -> writer, the writer/tools loop, and
    finishes at WRITER_EXIT_NODE. The caller attaches its own review node after
    that and routes back to WRITER_ENTRY_NODE for another attempt.
    """
    graph.add_node(WRITER_ENTRY_NODE, prepare_attempt_node)
    graph.add_node("writer", writer_node)
    graph.add_node("tools", ToolNode(tools.get_tools()))
    graph.add_node(WRITER_EXIT_NODE, extract_draft_node)

    graph.add_edge(START, WRITER_ENTRY_NODE)
    graph.add_edge(WRITER_ENTRY_NODE, "writer")

    graph.add_conditional_edges(
        "writer",
        route_after_writer,
        {"tools": "tools", WRITER_EXIT_NODE: WRITER_EXIT_NODE, END: END},
    )

    # Tool results go back to the writer so it can use them, not forward to the
    # reviewer. Routing them forward means the review runs against an empty
    # draft and the search results are silently discarded.
    graph.add_edge("tools", "writer")
