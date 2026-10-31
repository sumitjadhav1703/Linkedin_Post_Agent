# LinkedIn Post Agent

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.60-ff7f50)](https://langchain-ai.github.io/langgraph/)
[![NVIDIA](https://img.shields.io/badge/NVIDIA-Free_Endpoint-76B900?logo=nvidia&logoColor=white)](https://build.nvidia.com/meta/llama-3_3-70b-instruct?nim=hosted)
[![Tavily](https://img.shields.io/badge/Tavily-0.1.0-blue)](https://tavily.com/)
[![Vercel](https://img.shields.io/badge/Vercel-Deployed-000000?logo=vercel&logoColor=white)](https://linkedin-post-agent-two.vercel.app/)
[![Render](https://img.shields.io/badge/Render-Deployed-46E3B7?logo=render&logoColor=white)](https://linkedin-post-agent-6mrm.onrender.com)
[![Live Demo](https://img.shields.io/badge/Live_Demo-linkedin--post--agent--two.vercel.app-success)](https://linkedin-post-agent-two.vercel.app/)


![Application Preview](docs/screenshots/home.png)

A LangGraph-based intelligent agent that generates LinkedIn posts using two distinct execution models: a Human-in-the-Loop (HITL) workflow that pauses for explicit approval, and an autonomous loop that relies on an LLM-driven reviewer to iterate independently. By sharing the exact same writer chain, this project isolates the review mechanism to clearly demonstrate how human gating changes application architecture, state management, and deployment constraints.

## Demo

**Live Frontend:** [https://linkedin-post-agent-two.vercel.app/](https://linkedin-post-agent-two.vercel.app/)

*(Note: The backend may spin down after inactivity on the Render free tier, meaning the first request could take up to 30-60 seconds to wake up.)*

This project demonstrates two distinct generation flows:
- **Human-in-the-Loop (HITL):** Generates a draft, suspends execution, and waits for a human to approve or provide feedback.
- **Autonomous Generation:** Generates a draft, self-evaluates using a separate LLM reviewer node, and iteratively refines the post until it meets quality standards (up to a configured attempt limit).


## Why This Project?

Building reliable LLM applications often comes down to the tradeoff between autonomy and control. This project tackles the engineering problem of generating LinkedIn content by presenting two identical pipelines that diverge only at the review step.

Comparing human approval with autonomous execution reveals how "agentic" workflows behave differently under supervision. More importantly, it demonstrates how adding a human to the loop drastically changes the backend requirements: an autonomous process runs start-to-finish in a background job, whereas a human-gated process requires the graph state to be suspended, persisted, and accurately resumed later.

## Features

- **Human-in-the-Loop Workflow:** Pauses LangGraph execution using `interrupt()`, awaiting explicit human approval or revision instructions before proceeding.
- **Autonomous Workflow:** Utilizes a structured-output LLM reviewer to automatically grade drafts, passing feedback back to the writer for autonomous iteration.
- **Shared Core Logic:** Both workflows import the exact same LangChain generation sequence, ensuring accurate side-by-side comparison.
- **Web Search Augmentation:** Integrates the Tavily search tool (optional) to pull in current data when generating posts.
- **State Management:** Utilizes LangGraph's `MemorySaver` to checkpoint and resume in-process graph state.
- **React/Vite Frontend:** A dedicated client for testing both the interactive HITL flow and the polling-based autonomous background job.

## Human-in-the-Loop vs Autonomous

This project isolates the review mechanism to show how the architecture changes when a human is involved.

**Human-in-the-Loop (HITL)**
`User → Writer Node → Extracted Draft → Graph Suspends (interrupt) → Human Review (approve/reject) → Graph Resumes → Final Output`

Because the human review step takes time, the graph must pause. This requires a checkpointer (`MemorySaver` here) and a thread identity so the process can be put down and picked back up later. This single requirement dictates that subsequent requests must land on the same instance that holds the state in memory.

**Autonomous**
`User → Writer Node → Extracted Draft → LLM Reviewer Node (approve/reject) → Loop back to Writer → Final Output`

The autonomous loop requires neither suspension nor a checkpointer. It runs from start to finish in one background execution. The challenge here is ensuring the LLM reviewer's verdict is parsed reliably and that it knows when to stop iterating (e.g., maximum attempts).

## Architecture

```mermaid
flowchart LR
    subgraph shared["Shared Writer Chain (app/writer.py)"]
        direction LR
        P[prepare_attempt] --> W[writer]
        W -->|tool_calls| T[tools]
        T --> W
        W -->|prose| X[extract_draft]
    end
    X --> R{review}
    R -->|rejected| P
    R -->|approved / max attempts| E[END]
```

- **Frontend:** React + Vite + Tailwind UI
- **API Layer:** FastAPI exposing HTTP routes for starting and resuming graphs
- **Agent Orchestration:** LangGraph handling state graphs, conditional edges, and interrupts
- **LLM Engine:** NVIDIA API Catalog via LangChain for drafting and reviewing
- **Tooling:** Tavily Search for real-time web context

## Tech Stack

| Category | Technology |
|---|---|
| **Frontend** | React (19), Vite (8), Tailwind CSS (4), TypeScript |
| **Backend** | Python 3.13, FastAPI, Uvicorn |
| **Agent Orchestration** | LangGraph, LangChain Core |
| **AI/LLM** | NVIDIA (`langchain-nvidia-ai-endpoints`) |
| **Search/Tools** | Tavily (`langchain-tavily`) |
| **Deployment** | Vercel (Frontend), Render (Backend) |

## Project Structure

- `app/`
  - `api.py`: FastAPI routes handling the HITL and Auto endpoints.
  - `config.py`: Environment checks, model configurations, and logging setup.
  - `state.py`: The `PostState` schema shared by both graphs.
  - `writer.py`: The shared LangGraph chain (prepare, write, search, extract).
  - `reviewer.py`: The structured-output LLM reviewer for the autonomous graph.
  - `graph_hitl.py`: The HITL graph utilizing the `interrupt()` node and `MemorySaver`.
  - `graph_auto.py`: The autonomous graph utilizing the LLM reviewer node.
  - `jobs.py`: In-memory thread and job trackers.
- `cli_hitl.py` & `cli_auto.py`: Terminal-based runners for debugging without the API.
- `frontend/`: The React + Vite client application.


### Generated LinkedIn Post
![Generated LinkedIn Post](docs/screenshots/generated-post.png)

## How It Works

### 1. Human-in-the-Loop Flow
![Human-in-the-Loop](docs/screenshots/human-in-the-loop.png)

1. The frontend calls `POST /api/hitl/start` with a topic.
2. The `app_hitl` graph executes the shared writer chain.
3. Upon extracting the draft, the graph hits the `human_review` node, calls `interrupt()`, and pauses.
4. The API returns the draft to the frontend with an `awaiting_review` status.
5. The human reviews the draft and submits feedback via `POST /api/hitl/resume`.
6. The graph resumes. If approved, it routes to `END`. If rejected, it routes back to `prepare_attempt` with the feedback appended to the state.

### 2. Autonomous Flow
![Autonomous Mode](docs/screenshots/autonomous.png)

1. The frontend calls `POST /api/auto/start` with a topic, receiving an immediate HTTP 202 response and a `job_id`.
2. The `app_auto` graph begins executing in a background thread.
3. After the writer extracts a draft, it passes to the `reviewer` node, which prompts an LLM to evaluate the post.
4. The reviewer outputs a structured decision (approve/reject + critique).
5. The graph loops automatically until approved or the `MAX_ATTEMPTS` limit is reached.
6. The frontend polls `GET /api/auto/status/{job_id}` to stream the history of rejected drafts and the final output.

## Local Development

### Backend Setup

1. Clone the repository and configure the virtual environment:
   ```bash
   uv venv --python 3.13
   uv pip install --python .venv/bin/python -r requirements.txt
   ```
2. Create a `.env` file in the root directory (see Environment Variables).
3. Start the FastAPI server:
   ```bash
   .venv/bin/python -m uvicorn app.api:app --reload
   ```

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   Use `npm run build` to verify a production bundle.

## Environment Variables

| Variable | Used By | Purpose |
|---|---|---|
| `NVIDIA_API_KEY` | Backend | Required. Authenticates calls to the NVIDIA hosted API for both writing and reviewing. |
| `TAVILY_API_KEY` | Backend | Optional. Enables web search augmentation if present. |
| `LOG_LEVEL` | Backend | Optional. Sets Python logging level (e.g., INFO, DEBUG). |
| `MAX_ATTEMPTS` | Backend | Optional. Maximum revision rounds before the graph forces an end (default: 2; allowed range: 1–5). |
| `CORS_ORIGINS` | Backend | Optional. Allows specific frontend URLs to access the API. |
| `VITE_API_BASE` | Frontend | Optional. Defines the base URL the frontend uses to contact the backend (e.g., `http://localhost:8000`). |

*Note: Secrets must never be committed to Git. The backend checks for key presence without logging values.*

## API Documentation

### Human-in-the-Loop
- `POST /api/hitl/start`: Starts the flow. Accepts `{ "topic": "...", "enable_search": false }`. Returns the first draft, `thread_id`, and status `awaiting_review`.
- `POST /api/hitl/resume`: Submits feedback. Accepts `{ "thread_id": "...", "feedback": "approved | critique" }`. Returns either another draft (`awaiting_review`) or the final output (`completed`).

### Autonomous
- `POST /api/auto/start`: Initiates the background loop. Accepts `{ "topic": "...", "enable_search": false }`. Returns `202 Accepted` and a `job_id`.
- `GET /api/auto/status/{job_id}`: Polls for status. Returns job state (`running`, `completed`, or `error`), current attempt count, history of failed drafts, and the final draft.

### Health
- `GET /api/health`: Returns API key presence and current LLM model configuration.

## Deployment

**Frontend:** Deployed via Vercel at [https://linkedin-post-agent-two.vercel.app/](https://linkedin-post-agent-two.vercel.app/). It uses the `VITE_API_BASE` environment variable to point to the production backend.

**Backend:** Deployed via Render. It uses `CORS_ORIGINS` to allow requests explicitly from the Vercel frontend.

**Important Deployment Note:** The backend currently runs on Render's Free tier, which spins down after 15 minutes of inactivity.
- The first request after a sleep period may take longer (cold start).
- **Crucially:** Because the HITL flow relies on `MemorySaver` (an in-process Python dictionary), if the backend spins down while a draft is awaiting human review, the session state is lost, resulting in a 404 on the next resume request.

## Important Architecture / Design Decisions

- **Why LangGraph:** LangGraph provides native support for cyclical workflows (loops) and explicit interruptions. This makes it trivial to represent an iterative writing process that routes back on itself.
- **Shared Writer Logic:** By sharing the exact same `app/writer.py` pipeline, the comparison between HITL and Autonomous is isolated entirely to the review node, preventing prompt drift between the two modes.
- **In-Memory Checkpointing:** The project deliberately uses `MemorySaver` for state. While this means state is wiped on server restarts, it perfectly illustrates the architectural cost of human suspension: a real production deployment would require a persistent checkpointer (like Postgres or SQLite) to safely survive multi-instance scaling and cold starts.
- **Structured Output parsing:** The autonomous reviewer attempts to use Pydantic structured output. If unsupported, it fails closed to an anchored regex check, ensuring format drift results in a safe rejection rather than an unverified approval.

## Security and Limitations

- **No Authentication / Rate Limiting:** The API is unauthenticated and unprotected by rate limits. Anyone with the URL can trigger LLM generation. This is a deliberate tradeoff for a portfolio demo.
- **In-Memory Sessions:** As noted, scaling the backend beyond one instance or deploying on a scale-to-zero serverless platform (like Render Free) will result in lost HITL sessions because `MemorySaver` state cannot be shared across processes.
- **Error Handling Check:** The architecture explicitly checks for LLM failure states before suspension. If an API call fails, the graph routes straight to `END` and returns a safe error (429 for quota exhaustion, otherwise 502) rather than asking a human to review a system error.

## Future Improvements

- **Persistent Checkpoint Storage:** Replace `MemorySaver` with `PostgresSaver` or `SqliteSaver` to ensure HITL sessions survive process restarts and allow horizontal scaling.
- **Authentication & Rate Limiting:** Add basic API key validation or user sessions to protect LLM credits.
- **Production-Grade Deployment:** Upgrade backend hosting to an always-on tier to prevent cold starts and session eviction.
- **Evaluation Framework:** Introduce an evaluation metric (e.g., LangSmith) to score generated posts against successful real-world LinkedIn content.

## NVIDIA free endpoint setup

Both writer and reviewer use **`meta/llama-3.3-70b-instruct`**, currently listed
as a [Free Endpoint in NVIDIA's catalog](https://build.nvidia.com/meta/llama-3_3-70b-instruct?nim=hosted),
at `https://integrate.api.nvidia.com/v1`. The model is fixed in `app/config.py`;
there is no paid fallback or automatic provider switching. Free access remains
subject to NVIDIA account quotas and evaluation terms; it is not unlimited
production hosting. Check your account's current access before running it.

Create your own root `.env` containing the two backend variables:

```dotenv
NVIDIA_API_KEY=your_nvidia_key
TAVILY_API_KEY=your_tavily_key
```

The application loads them at runtime. The migration's offline checks disable
`.env` loading; real secret files are ignored by Git. Search is optional and
uses your Tavily allowance when enabled. A key's presence is not a guarantee
that the provider accepts it or that quota remains.

### Render backend and Vercel frontend

A local `.env` does **not** update deployed hosting environments.

1. On **Render**, deploy the updated backend with Python 3.13, install
   `requirements.txt`, and set `NVIDIA_API_KEY` and `TAVILY_API_KEY` in its
   environment settings. Start with
   `uvicorn app.api:app --host 0.0.0.0 --port $PORT --workers 1`.
2. Keep one worker and one instance: sessions, checkpoints, and background jobs
   are in memory. Restarts and instance replacement lose them. For a changed
   frontend hostname, set `CORS_ORIGINS` to the allowed origin(s), comma-separated.
3. On **Vercel**, keep `frontend` as the app root. Set public `VITE_API_BASE` to
   the Render backend's HTTPS URL, then rebuild. Never place provider secrets
   in variables prefixed with `VITE_`—those values go into browser bundles.
4. Deploy backend and frontend together: `/api/health` now returns
   `provider: "nvidia"` and `nvidia_key` instead of `groq_key`. Health reports
   key presence only. After configuring credentials, validate both workflows
   and optional search against your own account.

### Reliability changes

- Quota and authentication failures stop immediately; they are not retried.
- Network failures and HTTP 5xx get at most one application-level retry.
- Review uses one tool-schema request; only unsupported schemas or parsing
  failures permit a text-review fallback. A quota error cannot trigger fallback.
- Model output is bounded to 1,024 writer tokens and 512 reviewer tokens per
  call. Search tool rounds are capped per revision; after the cap the writer
  receives no tools and must produce prose. `MAX_ATTEMPTS` defaults to 2.
- Autonomous drafts are saved before review. A failed review leaves the latest
  draft and history available; it does not mark them approved. These failed
  jobs are terminal, not automatically resumed or resubmitted.
- API failures expose safe messages, not raw provider error bodies. Failed HITL
  sessions cannot accept another verdict; start a new session after preserving
  the visible draft. This migration does not add durable recovery.
- Browser requests have deadlines (15 seconds for health/status/start-job,
  180 seconds for HITL generation). A client timeout does not cancel server
  work. Check existing job status before starting another generation.

### Offline checks

```bash
# From the repository root; real .env files are deliberately not loaded.
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m unittest discover -s tests -v

# From frontend/; Node.js 24 is used in CI.
npm ci
npm test
npm run build
```

`requirements.in` lists direct Python dependencies; `requirements.txt` pins the
resolved set. To update it intentionally, use
`uv pip compile requirements.in --python 3.13 -o requirements.txt` and rerun
checks. Frontend packages are locked in `frontend/package-lock.json`.
[CI](.github/workflows/ci.yml) runs offline checks for both layers.

These tests use mocked provider responses. They establish routing, parsing,
error handling, and frontend compatibility—not live quota availability or
LinkedIn post quality. Existing screenshots predate this provider migration.
