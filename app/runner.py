"""Executes the autonomous graph as a background job.

Streams node-level updates rather than calling invoke(), so the job store fills
in with each draft and each verdict as they happen. That is what lets the
polling endpoint show the loop iterating instead of a spinner.
"""

import logging

from app import config, jobs
from app.graph_auto import app_auto
from app.state import initial_state
from app.writer import WRITER_ENTRY_NODE, WRITER_EXIT_NODE, stop_reason

logger = logging.getLogger(__name__)


def run_auto_job(job_id: str, topic: str, enable_search: bool) -> None:
    """Run the autonomous loop to completion, recording progress as it goes.

    Runs on a worker thread. Never raises: any failure is written to the job
    record so the polling endpoint can report it.
    """
    logger.info("Auto job %s starting: %r (search=%s)", job_id, topic, enable_search)

    state = initial_state(topic, enable_search)
    attempt = 0
    final: dict = {}

    try:
        for chunk in app_auto.stream(
            state,
            config={"recursion_limit": config.GRAPH_RECURSION_LIMIT},
            stream_mode="updates",
        ):
            for node, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                final.update(update)

                if node == WRITER_ENTRY_NODE:
                    attempt = update.get("attempt", attempt)
                elif node == WRITER_EXIT_NODE and update.get("draft"):
                    jobs.record_draft(job_id, attempt, update["draft"])
                elif node == "reviewer" and "is_approved" in update:
                    jobs.record_verdict(
                        job_id,
                        bool(update["is_approved"]),
                        update.get("review_feedback", ""),
                    )

                if update.get("error"):
                    raise RuntimeError(update["error"])

    except Exception as exc:  # noqa: BLE001 - the job record is the error channel
        logger.error("Auto job %s failed: %s", job_id, exc, exc_info=True)
        jobs.update_job(job_id, status="error", error=str(exc), stop_reason="error")
        return

    final.setdefault("attempt", attempt)
    reason = stop_reason(final)

    jobs.update_job(
        job_id,
        status="completed",
        draft=final.get("draft", ""),
        is_approved=bool(final.get("is_approved")),
        attempt=final.get("attempt", attempt),
        stop_reason=reason,
    )
    logger.info("Auto job %s completed after %d attempt(s): %s", job_id, attempt, reason)
