"""FastAPI layer over the two graphs.

Two modes, two route families, one deliberate architectural difference:
  /api/hitl/*  suspends on interrupt() and waits for a human verdict
  /api/auto/*  runs an LLM review loop to completion as a background job

Importing this module never blocks and never calls an LLM.
"""

import asyncio
import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel, Field

from app import config, jobs
from app.graph_hitl import REVIEW_INSTRUCTION, app_hitl
from app.llm import LLMError
from app.runner import run_auto_job
from app.state import initial_state
from app.writer import stop_reason

config.configure_logging()
logger = logging.getLogger(__name__)

api = FastAPI(
    title="LinkedIn Post Generator",
    description="Human-in-the-loop vs autonomous agent review loops.",
    version="1.0.0",
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- request models --------------------------------------------------------


class StartRequest(BaseModel):
    # No min_length: a blank topic is rejected in the handler so that both ""
    # and "   " return the same 400, rather than pydantic returning 422 for one
    # and the handler 400 for the other.
    topic: str = Field(max_length=500)
    enable_search: bool = False


class ResumeRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    feedback: str = Field(min_length=1, max_length=4000)


# --- helpers ---------------------------------------------------------------


def _graph_config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": config.GRAPH_RECURSION_LIMIT,
    }


def _interrupt_payload(result: dict) -> dict | None:
    """Pull the interrupt payload out of a graph result, if it paused."""
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value


def _hitl_response(thread_id: str, result: dict) -> dict:
    """Shape a HITL graph result into the API contract.

    Either the graph paused for another review, or it finished.
    """
    payload = _interrupt_payload(result)

    if payload is not None:
        jobs.update_session(thread_id, status="awaiting_review")
        return {
            "thread_id": thread_id,
            "status": "awaiting_review",
            "draft": payload["draft"],
            "attempt": payload["attempt"],
            "instruction": payload.get("instruction", REVIEW_INSTRUCTION),
        }

    if result.get("error"):
        jobs.update_session(thread_id, status="error")
        raise HTTPException(status_code=502, detail=result["error"])

    jobs.update_session(thread_id, status="completed")
    return {
        "thread_id": thread_id,
        "status": "completed",
        "draft": result.get("draft", ""),
        "attempt": result.get("attempt", 0),
        "is_approved": bool(result.get("is_approved")),
        "stop_reason": stop_reason(result),
    }


# --- routes ----------------------------------------------------------------


@api.get("/api/health")
def health() -> dict:
    """Report configuration and key presence. Never exposes key values."""
    return {
        "status": "ok",
        "groq_key": config.has_key(config.GROQ_KEY_NAME),
        "tavily_key": config.has_key(config.TAVILY_KEY_NAME),
        "writer_model": config.WRITER_MODEL,
        "reviewer_model": config.REVIEWER_MODEL,
        "max_attempts": config.MAX_ATTEMPTS,
    }


@api.post("/api/hitl/start")
async def hitl_start(request: StartRequest) -> dict:
    """Write a first draft and pause for human review."""
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic must not be empty")

    thread_id = jobs.create_session(topic, request.enable_search)
    logger.info("HITL session %s starting: %r", thread_id, topic)

    try:
        result = await asyncio.to_thread(
            app_hitl.invoke,
            initial_state(topic, request.enable_search),
            config=_graph_config(thread_id),
        )
    except LLMError as exc:
        jobs.update_session(thread_id, status="error")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("HITL session %s crashed: %s", thread_id, exc, exc_info=True)
        jobs.update_session(thread_id, status="error")
        raise HTTPException(status_code=500, detail=f"Graph failed: {exc}") from exc

    return _hitl_response(thread_id, result)


@api.post("/api/hitl/resume")
async def hitl_resume(request: ResumeRequest) -> dict:
    """Resume a paused session with the human's verdict."""
    thread_id = request.thread_id

    if jobs.get_session(thread_id) is None:
        # In-memory sessions do not survive a restart or an eviction, and the
        # frontend needs to tell that apart from a bad id.
        raise HTTPException(
            status_code=404,
            detail="Unknown or expired thread_id. Start a new session.",
        )

    logger.info("HITL session %s resuming", thread_id)

    try:
        result = await asyncio.to_thread(
            app_hitl.invoke,
            Command(resume=request.feedback),
            config=_graph_config(thread_id),
        )
    except LLMError as exc:
        jobs.update_session(thread_id, status="error")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("HITL session %s crashed: %s", thread_id, exc, exc_info=True)
        jobs.update_session(thread_id, status="error")
        raise HTTPException(status_code=500, detail=f"Graph failed: {exc}") from exc

    return _hitl_response(thread_id, result)


@api.post("/api/auto/start", status_code=202)
async def auto_start(request: StartRequest, background: BackgroundTasks) -> dict:
    """Kick off the autonomous loop and return immediately."""
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic must not be empty")

    job_id = jobs.create_job(topic, request.enable_search)
    background.add_task(
        asyncio.to_thread, run_auto_job, job_id, topic, request.enable_search
    )

    return {"job_id": job_id, "status": "running"}


@api.get("/api/auto/status/{job_id}")
def auto_status(job_id: str) -> dict:
    """Poll an autonomous job. History grows as the loop iterates."""
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id.")

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "attempt": job["attempt"],
        "history": job["history"],
        "draft": job["draft"],
        "is_approved": job["is_approved"],
        "stop_reason": job["stop_reason"],
        "error": job["error"],
    }


# `uvicorn app.api:app` is the conventional spelling, so expose both names.
app = api
