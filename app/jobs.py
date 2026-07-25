"""In-process stores for autonomous jobs and human-in-the-loop sessions.

Both are plain dicts behind a lock, capped and evicted oldest-first. This is a
deliberate demo-scale choice: it means the app must run as a single worker, and
a restart drops in-flight work. See PLAN.md for what that constrains about
hosting.
"""

import logging
import threading
import uuid
from collections import OrderedDict
from typing import Any, Optional

from app import config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: "OrderedDict[str, dict]" = OrderedDict()
_sessions: "OrderedDict[str, dict]" = OrderedDict()


def new_id() -> str:
    """Server-side identifier. Clients never invent these."""
    return uuid.uuid4().hex


def _evict(store: OrderedDict, limit: int) -> None:
    while len(store) > limit:
        dropped, _ = store.popitem(last=False)
        logger.info("Evicted oldest entry %s to stay under the %d cap", dropped, limit)


# --- autonomous jobs -------------------------------------------------------


def create_job(topic: str, enable_search: bool) -> str:
    job_id = new_id()
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "topic": topic,
            "enable_search": enable_search,
            "attempt": 0,
            "history": [],
            "draft": None,
            "is_approved": None,
            "stop_reason": None,
            "error": None,
        }
        _evict(_jobs, config.MAX_TRACKED_JOBS)
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def update_job(job_id: str, **fields: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(fields)


def record_draft(job_id: str, attempt: int, draft: str) -> None:
    """Append a new attempt to the job history as soon as its draft exists."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job["attempt"] = attempt
        job["history"].append(
            {"attempt": attempt, "draft": draft, "approved": None, "feedback": None}
        )


def record_verdict(job_id: str, approved: bool, feedback: str) -> None:
    """Attach the reviewer's verdict to the most recent attempt."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or not job["history"]:
            return
        job["history"][-1]["approved"] = approved
        job["history"][-1]["feedback"] = feedback


# --- human-in-the-loop sessions -------------------------------------------


def create_session(topic: str, enable_search: bool) -> str:
    thread_id = new_id()
    with _lock:
        _sessions[thread_id] = {
            "thread_id": thread_id,
            "topic": topic,
            "enable_search": enable_search,
            "status": "awaiting_review",
        }
        _evict(_sessions, config.MAX_TRACKED_SESSIONS)
    return thread_id


def get_session(thread_id: str) -> Optional[dict]:
    with _lock:
        session = _sessions.get(thread_id)
        return dict(session) if session else None


def update_session(thread_id: str, **fields: Any) -> None:
    with _lock:
        session = _sessions.get(thread_id)
        if session is not None:
            session.update(fields)
