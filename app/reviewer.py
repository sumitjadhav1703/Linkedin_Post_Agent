"""The autonomous reviewer node — the one thing the auto graph has that the
human-in-the-loop graph does not.

Verdict extraction goes through three tiers, in order:
  1. structured output via a Pydantic model (no parsing at all)
  2. anchored regex on `VERDICT:` if structured output is unavailable
  3. fail closed — treat an unparseable review as a rejection

Tier 3 matters: failing closed costs one extra revision loop, bounded by
MAX_ATTEMPTS, whereas failing open ships a post that was never actually graded.
"""

import logging
import re

from pydantic import BaseModel, Field

from app import config, prompts
from app.llm import LLMError, invoke_with_retry, make_reviewer_llm
from app.state import PostState

logger = logging.getLogger(__name__)

# Anchored on the VERDICT label. An unanchored substring test misreads a
# rejection worded "VERDICT: REJECTED (this is not approved yet)" as approval,
# because the prose contains the word "approved".
_VERDICT_RE = re.compile(r"VERDICT\s*:\s*\**\s*(APPROVED|REJECTED)", re.IGNORECASE)
_FEEDBACK_RE = re.compile(r"FEEDBACK\s*:\s*\**\s*(.+)", re.IGNORECASE | re.DOTALL)


class ReviewVerdict(BaseModel):
    """The reviewer's decision, as a typed object."""

    approved: bool = Field(
        description="True only if the post meets every criterion and is publish-ready."
    )
    feedback: str = Field(
        description="One short paragraph of specific, actionable critique."
    )


_reviewer_llm = None
_structured_reviewer = None
_structured_output_broken = False


def _get_reviewers():
    global _reviewer_llm, _structured_reviewer
    if _reviewer_llm is None:
        _reviewer_llm = make_reviewer_llm()
        _structured_reviewer = _reviewer_llm.with_structured_output(ReviewVerdict)
    return _reviewer_llm, _structured_reviewer


def parse_verdict_text(text: str) -> ReviewVerdict:
    """Fallback parser for free-text reviews. Fails closed."""
    match = _VERDICT_RE.search(text)

    feedback_match = _FEEDBACK_RE.search(text)
    feedback = feedback_match.group(1).strip() if feedback_match else text.strip()

    if match is None:
        logger.warning(
            "Reviewer response carried no parseable VERDICT line — treating as "
            "rejected and passing the raw text back as feedback."
        )
        return ReviewVerdict(approved=False, feedback=feedback)

    return ReviewVerdict(approved=match.group(1).upper() == "APPROVED", feedback=feedback)


def _review_with_fallback(draft: str) -> ReviewVerdict:
    """Try structured output, fall back to text parsing on failure."""
    global _structured_output_broken

    plain_llm, structured_llm = _get_reviewers()
    user_prompt = f"Review this LinkedIn post draft:\n\n{draft}"

    if not _structured_output_broken:
        try:
            result = invoke_with_retry(
                structured_llm,
                [
                    ("system", prompts.REVIEWER_SYSTEM_PROMPT),
                    ("human", user_prompt),
                ],
                what="reviewer (structured)",
            )
            if isinstance(result, ReviewVerdict):
                return result
            # Some providers hand back a dict rather than the model instance.
            if isinstance(result, dict):
                return ReviewVerdict(**result)
            logger.warning(
                "Structured reviewer returned %s, not a verdict — falling back.",
                type(result).__name__,
            )
        except Exception as exc:  # noqa: BLE001
            # Includes LLMError. Latch the failure so a provider that does not
            # support structured output does not pay the retry cost every loop.
            _structured_output_broken = True
            logger.warning(
                "Structured output unavailable (%s) — using the text parser from "
                "here on.",
                exc,
            )

    response = invoke_with_retry(
        plain_llm,
        [
            (
                "system",
                prompts.REVIEWER_SYSTEM_PROMPT + prompts.REVIEWER_FORMAT_INSTRUCTION,
            ),
            ("human", user_prompt),
        ],
        what="reviewer (text)",
    )
    return parse_verdict_text(str(response.content))


def reviewer_node(state: PostState) -> dict:
    """Grade the draft and decide whether to approve or send it back."""
    # Mirrors the guard in the human review node: a failed run is not reviewed.
    if state.get("error"):
        return {}

    draft = state.get("draft", "")

    if not draft:
        logger.error("Reviewer reached with no draft to review")
        return {"error": "Reviewer received an empty draft."}

    try:
        verdict = _review_with_fallback(draft)
    except LLMError as exc:
        logger.error("Reviewer node failed: %s", exc)
        return {"error": str(exc)}

    logger.info(
        "Attempt %d/%d verdict: %s",
        state["attempt"],
        config.MAX_ATTEMPTS,
        "APPROVED" if verdict.approved else "REJECTED",
    )
    logger.debug("Reviewer feedback: %s", verdict.feedback)

    return {
        "is_approved": verdict.approved,
        "review_feedback": verdict.feedback,
    }
