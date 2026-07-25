# LinkedIn Post Generator — HITL vs Autonomous demo

## Context

Two standalone LangGraph CLI scripts (`Human_in_the_Loop.py`, `Iterative_Tools.py`) each generate LinkedIn posts, one gated by a human `interrupt()` and one by an LLM reviewer node. The goal is a portfolio demo where a frontend toggle picks a mode and calls a different backend route, so an interviewer can see the architectural tradeoff between human-gated and fully autonomous agent review loops.

They don't currently make that point. The two graphs differ in writer model, provider, prompt wording, tool access, and state shape — so any observed difference in output is confounded and the comparison is not honest. On top of that the autonomous graph has a wiring bug that makes its reviewer read an empty draft, and both scripts are blocking CLI programs with no API, no error handling, and `print()` observability.

Outcome: one shared writer pipeline, two graphs that differ in exactly one node, a FastAPI layer with server-generated session IDs, and honest failure surfacing. Demo-scale, not production-scale.

---

## Step 1 — Audit findings

Your summary of the two graphs is accurate. Confirmed:

- `Human_in_the_Loop.py`: writer node + `human_review_node` using `interrupt()`, `ChatMistralAI("mistral-small")`, `MemorySaver`, `thread_id="linkedin_session_1"` (line 136), CLI `input()` loop.
- `Iterative_Tools.py`: writer with `TavilySearch` bound, `reviewer_node` on `ChatGroq("llama-3.3-70b-versatile")`, no checkpointer, `.compile()` with no config.

### Additional problems you did not list

**A. Autonomous graph is mis-wired — the reviewer reviews an empty string.** `Iterative_Tools.py:173` is `graph.add_edge("tools", "reviewer")`. After the writer emits tool calls and `ToolNode` runs, control goes straight to the reviewer, skipping both `extract_draft` and any second writer call. `state["draft"]` is still `""` from `initial_state`, so `reviewer_node` grades an empty post. The edge must be `tools -> writer`. This is the most serious defect in the repo and it silently produces plausible-looking output.

**B. The writer never sees its own tool results.** `writer_node` (`Iterative_Tools.py:76`) rebuilds `messages = [system, user_message]` from scratch every call and ignores `state["messages"]`. Even with edge A fixed, Tavily results would be discarded. Search is currently decorative in both the wiring and the message flow.

**C. The reviewer's verdict parse has a false-positive path, not just fragility.** `"APPROVED" in review_text.upper().split("FEEDBACK")[0]` (`Iterative_Tools.py:125`) — a rejection phrased `VERDICT: REJECTED (this is not approved yet)` uppercases to contain the substring `APPROVED` and is misread as an approval. Your item 5 called this fragile; it is actively wrong.

**D. Both files run their CLI at module import time.** The `print`/`input`/`invoke` block sits at module level (`Human_in_the_Loop.py:122-169`, `Iterative_Tools.py:183-215`). Any `import` from FastAPI blocks on `input()`. Must move under `if __name__ == "__main__":` before anything can import these graphs.

**E. Model IDs.** Verified against vendor docs:
- `mistral-7b-instruct` — **retired**, not a valid Mistral API ID (it's the HuggingFace weights name). Confirms your item 2.
- `mistral-small` bare — **deprecated**, no longer a supported alias; use `mistral-small-latest` (currently resolves to Mistral Small 4, `mistral-small-4-0-26-03`).
- `llama-3.3-70b-versatile` — **deprecated by Groq on 2026-06-17** for free and developer tiers. You did not flag this one. Moot given the decision below to drop Groq.

**F. Minor:** `messages`/`add_messages` is declared but entirely unused in the HITL `State`. `state['review_feedback']` is accessed by direct key in the auto writer (`Iterative_Tools.py:62`) vs `.get()` in HITL. `import os` unused in both files. `human_review_node` prints before `interrupt()`, so the print repeats on every resume — harmless now, but a reminder that anything before an `interrupt()` re-executes on resume.

**G. `.venv/` is empty** — zero packages in `site-packages`. `requirements.txt` is also missing `langchain-mistralai` and `langchain-tavily` (both imported), and carries six unused deps (`faiss-cpu`, `sentence-transformers`, `pypdf`, `langchain-huggingface`, `langchain-community`, `langchain-text-splitters`). Nothing here has been run in this venv.

**H. Env keys not verifiable from my side.** Per your guardrail I did not open `.env`; `MISTRAL_API_KEY`, `GROQ_API_KEY`, `TAVILY_API_KEY` are all absent from the shell environment, which is expected since `load_dotenv()` supplies them. **Please confirm `MISTRAL_API_KEY` and `TAVILY_API_KEY` are set** — after the decisions below, `GROQ_API_KEY` is no longer needed.

### Decisions taken (from your answers)

- Writer **and** reviewer both on Mistral. Groq dropped entirely — one key, one failure surface, and the graphs then differ only in review mechanism.
- Tavily search in **both** graphs, with bugs A and B fixed so it actually works.
- Auto mode runs as a **background job with polling**.

### One thing I'd do differently from your instructions

Your item 1 says "same base system prompt". I'd go further: the two graphs should share the *same writer node object*, not two copies of a matching prompt. Copies drift. The plan below extracts one `writer.py` imported by both graph modules, so the shared path is physically impossible to diverge.

---

## Step 2 — Design

### Module structure

```
Proj/
  app/
    __init__.py
    config.py        # env presence checks, model IDs, MAX_ATTEMPTS, logging setup
    state.py         # PostState TypedDict (shared)
    prompts.py       # WRITER_SYSTEM_PROMPT, REVIEWER_SYSTEM_PROMPT
    llm.py           # LLM factories + invoke_with_retry() + LLMError
    tools.py         # Tavily tool, degrades to [] when key absent
    writer.py        # prepare_attempt / writer / tools / extract_draft  (SHARED)
    reviewer.py      # structured-output reviewer + regex fallback
    graph_hitl.py    # shared writer chain + human_review interrupt node
    graph_auto.py    # shared writer chain + reviewer node
    jobs.py          # in-memory job store for auto mode
    api.py           # FastAPI app
  cli_hitl.py        # old CLI behaviour, preserved, imports app.graph_hitl
  cli_auto.py
  PLAN.md            # this plan, committed to the repo
  requirements.txt
```

`Human_in_the_Loop.py` and `Iterative_Tools.py` are replaced by `cli_hitl.py` / `cli_auto.py`. They stay runnable so the CLI demo still works.

### Shared state (`state.py`)

```python
class PostState(TypedDict):
    topic: str
    messages: Annotated[list, add_messages]
    draft: str
    review_feedback: str
    is_approved: bool
    attempt: int
    error: str | None          # new: set by any node that fails
    enable_search: bool        # new: per-request toggle
```

Both graphs use this exact type. `messages` becomes load-bearing (it carries tool results), fixing finding F.

### Shared writer chain (`writer.py`) — used verbatim by both graphs

The single writer node is split into four so the tool loop is correct:

| Node | Role |
|---|---|
| `prepare_attempt` | Pure Python. Increments `attempt`, appends the instruction `HumanMessage` — the initial topic prompt on attempt 1, the revision prompt carrying `review_feedback` afterwards. No LLM call. |
| `writer` | Invokes the writer LLM on `[SystemMessage] + state["messages"]`, so it sees the full history including prior drafts, feedback, and `ToolMessage` results. Appends the response. |
| `tools` | `ToolNode([TavilySearch])`, default `handle_tool_errors=True` so a Tavily failure returns as a `ToolMessage` rather than crashing the graph. |
| `extract_draft` | Pulls `.content` off the last AI message into `draft`. |

Edges: `prepare_attempt -> writer`, then conditional on `writer` — `tools` if `response.tool_calls` else `extract_draft` — and critically **`tools -> writer`** (fixes finding A), letting the writer consume search results and then produce prose.

Message objects are `langchain_core.messages` classes, not `("role", "text")` tuples, because `add_messages` and `ToolNode` need real `ToolMessage`/`AIMessage` instances to pair tool calls with results.

### The two graphs — one node apart

```
HITL:  START -> prepare_attempt -> writer ⇄ tools -> extract_draft -> human_review -> {END | prepare_attempt}
AUTO:  START -> prepare_attempt -> writer ⇄ tools -> extract_draft -> reviewer     -> {END | prepare_attempt}
```

Everything left of the review node is imported from `writer.py`. `graph_hitl.py` compiles with `MemorySaver()`; `graph_auto.py` compiles with no checkpointer. That single node substitution is the entire demo thesis, and it's now literally the only difference in the code.

Shared router `should_continue(state)`: returns `END` if `state["error"]`, `END` if `is_approved`, `END` if `attempt >= MAX_ATTEMPTS` (3), else `prepare_attempt`.

### FastAPI routes (`api.py`)

| Route | Behaviour |
|---|---|
| `POST /api/hitl/start` | `uuid4().hex` thread_id, invoke to first `interrupt()`, return draft |
| `POST /api/hitl/resume` | `Command(resume=feedback)`, return next draft or final post |
| `POST /api/auto/start` | `uuid4().hex` job_id, kick off background task, return `202` immediately |
| `GET /api/auto/status/{job_id}` | poll status + per-attempt history |
| `GET /api/health` | reports which API keys are present (names only, never values) |

Background execution: `asyncio.to_thread(app_auto.invoke, ...)` launched via `BackgroundTasks`, results written into a module-level `JOBS: dict[str, dict]` guarded by a lock, capped at ~100 entries with oldest-first eviction. `MemorySaver` and `JOBS` are both in-process — correct for a single-worker demo, and the deployment note below flags what that implies for hosting.

`SESSIONS: dict[thread_id, meta]` tracks live HITL threads so `/resume` can return a real `404` for an unknown or expired id instead of silently starting a fresh graph run.

---

## Step 3 — Alignment

1. Both writers: `ChatMistralAI(model="mistral-small-latest", temperature=0.7)` from `config.py`. Reviewer: same model at `temperature=0.2`. Fixes your item 2 and finding E.
2. One `WRITER_SYSTEM_PROMPT` in `prompts.py`, imported by both. Merges the two existing prompts, keeping the search clause since search is now in both graphs.
3. One `prepare_attempt` node owns all topic/feedback prompt construction, so the two graphs cannot phrase the revision instruction differently.
4. Delete `langchain-groq` and the Groq reviewer.

## Step 4 — Hardening

**Verdict parsing.** `reviewer.py` defines a Pydantic model and calls `.with_structured_output()`:

```python
class ReviewVerdict(BaseModel):
    approved: bool
    feedback: str
```

Fallback chain, in order: structured output → on exception, plain invoke + anchored regex `r"VERDICT\s*:\s*(APPROVED|REJECTED)"` (anchoring on `VERDICT:` is what kills the finding-C false positive, since a stray "not approved" in prose no longer matches) → on no match, **fail closed**: `approved=False`, `feedback=<raw text>`, logged at `WARNING`. Failing closed means format drift costs an extra revision loop rather than shipping an ungraded post; `MAX_ATTEMPTS` bounds the cost.

**Error handling.** `llm.py` exposes `invoke_with_retry(llm, messages, what=...)`: 2 retries with exponential backoff, raising a typed `LLMError` on final failure. Every node wraps its LLM call, catches `LLMError`, and returns `{"error": str(e)}` instead of raising. The router sends any state carrying `error` straight to `END`, and the API turns it into `502 {"status": "error", "error": ...}`. The process never dies from a provider hiccup — the frontend sees the failure.

**Missing keys.** `tools.py` returns `[]` and logs `WARNING` when `TAVILY_API_KEY` is absent; the writer then binds no tools and writes unaugmented. Absent `MISTRAL_API_KEY` fails fast at startup with a clear message. Neither path ever reads or prints `.env`.

**Logging.** `logging` configured once in `config.py`, level from `LOG_LEVEL` (default `INFO`). `INFO` for node entry/exit, attempt number, verdict. `DEBUG` for full draft text. `WARNING` for fallback parse and degraded search. `ERROR` for LLM failures with traceback. Every `print()` in the graph modules is removed; the CLI scripts keep `print()` since that is their user interface.

## Step 5 — API contract (also answers Step 7)

All bodies JSON. `thread_id` and `job_id` are always generated server-side; the frontend echoes back what it was given and never invents one.

**`POST /api/hitl/start`**
```jsonc
// request
{ "topic": "string, required, non-empty", "enable_search": false }
// 200
{ "thread_id": "hex", "status": "awaiting_review", "draft": "...", "attempt": 1,
  "instruction": "Type 'approved' to accept, or type your feedback to request a rewrite." }
// 400 empty topic · 502 { "status": "error", "error": "..." }
```

**`POST /api/hitl/resume`**
```jsonc
// request
{ "thread_id": "hex from start", "feedback": "approved | free-text critique" }
// 200 — another round
{ "thread_id": "...", "status": "awaiting_review", "draft": "...", "attempt": 2, "instruction": "..." }
// 200 — finished
{ "thread_id": "...", "status": "completed", "draft": "...", "attempt": 2,
  "is_approved": true, "stop_reason": "approved" }   // or "max_attempts"
// 404 unknown/expired thread_id · 502 on LLM error
```
The frontend loops on `status`: keep showing the review box while `awaiting_review`, render the final post on `completed`. `stop_reason` lets it distinguish "the human approved this" from "we ran out of attempts" — worth surfacing, it's part of the story the demo tells.

**`POST /api/auto/start`**
```jsonc
// request
{ "topic": "string, required", "enable_search": false }
// 202
{ "job_id": "hex", "status": "running" }
```

**`GET /api/auto/status/{job_id}`**
```jsonc
// 200
{ "job_id": "hex",
  "status": "running" | "completed" | "error",
  "attempt": 2,
  "history": [ { "attempt": 1, "draft": "...", "approved": false, "feedback": "..." } ],
  "draft": "...",            // present when completed
  "is_approved": true,       // present when completed
  "stop_reason": "approved", // or "max_attempts"; present when completed
  "error": null }
// 404 unknown job_id
```
Poll every ~1.5s while `running`. `history` grows as the loop iterates, so the UI can render each rejected draft with the reviewer's critique — that visible iteration is the demo's payoff, and it's the reason background+polling beats a single blocking call here.

**`GET /api/health`** → `{ "mistral_key": true, "tavily_key": false, "max_attempts": 3 }` — key **presence** only.

CORS: `allow_origins` from a `CORS_ORIGINS` env var, defaulting to `http://localhost:5173` and `http://localhost:3000`.

## Step 6 — Deployment research

Dispatch one research sub-agent, in parallel with the code work, covering Railway / Render / Fly.io / Modal / Cloud Run: hobby-tier cost, long-running background task support, polling and WebSocket behaviour, request timeout ceilings, and specifically the gotchas of `interrupt()` + `MemorySaver` under serverless (in-process checkpointer + cold starts + multi-instance routing means a resume can land on an instance that never saw the interrupt — the central risk to name). Deliverable: comparison table plus a single recommendation.

## Step 7

Answered inline in Step 5 above.

---

## Files

Created: `app/{__init__,config,state,prompts,llm,tools,writer,reviewer,graph_hitl,graph_auto,jobs,api}.py`, `cli_hitl.py`, `cli_auto.py`, `PLAN.md`.
Replaced: `Human_in_the_Loop.py`, `Iterative_Tools.py` (logic moves into `app/`; CLI entry points preserved as `cli_*.py`).
Rewritten: `requirements.txt` → `langgraph`, `langchain-core`, `langchain-mistralai`, `langchain-tavily`, `fastapi`, `uvicorn[standard]`, `pydantic`, `python-dotenv`. Drops `langchain-groq` and the six unused ML deps.

`.env` is never read, printed, or logged. Key checks go through `os.environ` key names only.

## Verification

1. `.venv/bin/pip install -r requirements.txt` — the venv is currently empty, so this is a real install, not a no-op.
2. `.venv/bin/python -c "import app.api"` — proves finding D is fixed (no `input()` at import).
3. Assert the graphs differ by one node: `diff <(grep add_node app/graph_hitl.py) <(grep add_node app/graph_auto.py)` should show only `human_review` vs `reviewer`.
4. `uvicorn app.api:app --reload`, then curl in order: `/api/health`; `/api/hitl/start` with a topic; `/api/hitl/resume` with critique feedback (expect `awaiting_review`, `attempt: 2`); `/api/hitl/resume` with `"approved"` (expect `completed`); `/api/auto/start` then poll `/api/auto/status/{job_id}` until `completed` and confirm `history` has one entry per attempt.
5. Reviewer fallback: temporarily force the structured-output call to raise, confirm the regex path runs, and confirm a draft whose review text contains the phrase "not approved" is classified **rejected** — the finding-C regression test.
6. Error path: run with a deliberately bad `MISTRAL_API_KEY` value in the process env and confirm a `502` JSON body rather than a stack trace and a dead process.
7. Search path: with `TAVILY_API_KEY` present, use a topic needing current data and confirm from `INFO` logs that a tool call fires and the writer runs *again afterwards* (proves finding A fixed); with the key absent, confirm the `WARNING` and a normal unaugmented post.
8. `.venv/bin/python cli_hitl.py` and `cli_auto.py` still work interactively.

---

# Implementation notes (post-build)

What changed from the plan during implementation, and what was verified live.

## Deviations from the plan

**Empty-topic status code.** The plan said `400`. Pydantic's `min_length=1` fired first and returned `422` for `""` while a whitespace-only topic fell through to the handler's `400` — two codes for the same user error. `min_length` was dropped from the model so both cases return `400` from one code path.

**A bug the plan did not anticipate, found in error-path testing.** With an invalid API key, `/api/hitl/start` returned `HTTP 200` with a draft — and the "draft" was the instruction prompt text. The writer node correctly caught the failure and set `state["error"]`, but `route_after_writer` still sent the run on to `extract_draft`, which read `messages[-1]` (still the un-answered `HumanMessage`) and treated it as the post. The graph then interrupted normally and the human was asked to approve a prompt. The error existed in state but no router ever saw it, because the interrupt happened first.

Three changes fix it, all in the shared chain so both graphs get them identically:
- `route_after_writer` routes to `END` on error, not to `extract_draft`.
- `extract_draft_node` returns an error unless the last message is an `AIMessage`.
- Both review nodes return `{}` immediately when an error is set, so `interrupt()` never fires on a failed run and `route_after_review` can end it.

This is the kind of failure the original code would have shipped silently, and it is worth mentioning in an interview: the error was *recorded* correctly and still produced a wrong-looking-right response, because nothing checked it before the graph paused.

**Search-round cap added.** `MAX_TOOL_ROUNDS = 2` in `writer.py`, not in the plan. A model that keeps deciding to search could otherwise stall a live demo.

**`GRAPH_RECURSION_LIMIT = 60`** added to config. LangGraph's default of 25 is tight once `MAX_ATTEMPTS` rounds are multiplied by the search loop.

## Verified live

| Check | Result |
|---|---|
| `import app.api` | No `input()` at import time |
| Graph node diff | Exactly one line: `human_review` vs `reviewer` |
| Verdict parser regression | The old parser reads `VERDICT: REJECTED (this is not approved yet)` as **approved**; the anchored parser reads it as rejected. Also correct on lowercase, `**bold**`, and unlabelled text (fails closed) |
| Structured output | Worked natively on Mistral — the regex fallback never fired |
| HITL cycle | start → `awaiting_review` a1 → resume with critique → `awaiting_review` a2 (draft visibly addressed the feedback) → resume `approved` → `completed`, `stop_reason: approved` |
| Auto job + polling | `202` → history grew 1→2→3 across polls → `completed` after 3 attempts, 2 rejections with substantive feedback |
| Search path | Node order `prepare_attempt → writer → tools → writer → extract_draft → reviewer` — tool results reach the writer |
| Bad API key | `/hitl/start` → `502`; auto job → `status: error`; process stayed up and `/api/health` kept answering |
| Unknown `thread_id` / `job_id` | `404` both |
| Blank and whitespace topic | `400` both |
| Both CLIs | Run to completion, correct `stop_reason` |

## Not done

No README. No frontend. No tests committed — the verification above was run ad hoc rather than written into a test file, which is the first thing worth adding if this grows.
