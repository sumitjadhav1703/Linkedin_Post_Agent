# Copy Desk — frontend

A single-page client for the LangGraph post generator in the parent directory. It
runs the same writer two ways and makes the difference visible: one mode stops and
waits for a human verdict, the other watches a second model rule on the draft.

## Run

The backend has to be up first — this app has no server of its own and no mock.

```bash
# in the parent directory
.venv/bin/python -m uvicorn app.api:app --port 8000 --reload

# here
npm install
npm run dev          # http://localhost:5173
```

Port 5173 is pinned with `strictPort` because the backend's CORS allowlist names it
explicitly. If Vite silently moved to 5174, every request would fail preflight.

Point it somewhere else with `VITE_API_BASE` (see `.env.example`); it defaults to
`http://localhost:8000`.

```bash
npm run build        # tsc --noEmit && vite build
npm run typecheck
```

## Layout

```
src/
  lib/api.ts             the only module that calls fetch; types mirror the API contract
  hooks/useHealth.ts     one call on load; max_attempts and model names come from here
  hooks/useHitlSession.ts   start -> resume -> resume; never polls
  hooks/useAutoSession.ts   start -> poll every 1500ms; stops on completed/error/unmount
  hooks/useElapsed.ts    the autonomous run's clock
  components/HitlDesk.tsx   manuscript + editor's rail + transcript of earlier rounds
  components/AutoLedger.tsx one row per attempt, appended as history grows
  index.css              design tokens, light/dark, the two palette temperatures
```

Plain `useState` throughout. No router — there is one screen. No state library.

## Notes on the two modes

They are laid out as different rooms on purpose, because they are different
interactions rather than one form with a swapped endpoint.

**Human in the loop** is warm, wide, and still. While it waits it shows no spinner
and no timer: the graph is suspended on `interrupt()` and genuinely nothing is
running, possibly forever. A spinner there would be a lie. The rail states the
attempt budget, and on the last round the rewrite button changes to *End without
approving* — because the backend's loop router ends the run when a rejection lands
on the final attempt instead of rewriting once more.

**Autonomous** is cool, dense, and ticking, under a `.machine` palette shift. It
carries a telemetry strip — status, elapsed clock, attempt, poll count — and a
ledger that appends a row per attempt. Rejected drafts stay on screen with the
critique that killed them.

`stop_reason` is never rendered as a generic "done": *approved* and *max_attempts*
get different colours and different words, because "this passed" and "we ran out of
tries, here's the last one" are different outcomes.

## Failure handling

- **400** — blank topics are caught in the form; the request is never sent.
- **404** — the session is gone from the server's memory. Retrying is pointless, so
  only *Start over* is offered, and the copy explains why it happened.
- **502** — the model call failed; `detail` is shown verbatim with a retry that
  resends the same feedback.
- **Network** — a poll tolerates two dropped requests before giving up, so a blip
  doesn't kill a run that is still going server-side. Nothing leaves a spinner
  running forever, and the masthead flips to *Backend stopped answering* once a
  request fails to connect, rather than leaving the load-time green light up.

Every interval is cleared on completion, on error, on a new run, and on unmount.

## Accessibility

`prefers-color-scheme` drives the theme through CSS variables, so there is no class
toggle and no first-paint flash. The mode toggle is a real tablist with arrow-key
navigation. The autonomous timeline announces through a dedicated `role="status"`
region carrying one short sentence per change — putting `aria-live` on the timeline
itself would re-read every draft on screen every 1.5 seconds.
