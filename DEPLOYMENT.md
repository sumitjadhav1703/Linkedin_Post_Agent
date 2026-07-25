# Deployment notes

Research current as of July 2026. Cost and limit claims are linked at the bottom.

## Comparison

| Platform | Free tier | Cost here | Scales to zero (disable?) | Cold start | Pin to 1 instance | Background work after response | Request timeout | Deploy |
|---|---|---|---|---|---|---|---|---|
| **Railway** | No usable ongoing free tier — one-time $5 trial credit, then $1/mo non-rollover | Hobby: $5/mo floor + metered CPU/RAM/egress, realistically $5–10/mo | Yes — "App Sleeping" toggle (sleeps after ≥10 min idle); **toggle off = always-on** | N/A once always-on | Yes — single replica by default, autoscaling is opt-in | Yes, fully — persistent container, no CPU throttling | ~15 min HTTP soft cap; WebSockets exempt | Git push → Nixpacks auto-detects Python, or your Dockerfile; env vars in dashboard |
| **Render** | Yes, but **spins down after 15 min idle** (cut from 30) and 5 GB/mo bandwidth since the Apr 2026 revamp | Starter: **$7/mo flat**, always-on | Free tier only; Starter has no sleep by design | Free tier ~30–60s, up to 2–3 min reported | Yes — Starter is a single fixed instance | Yes, fully | Standard HTTP/WebSocket, no special SSE config | Git push auto-deploy, Dockerfile or native runtime |
| **Fly.io** | **None since 2024** — 2 VM-hour trial only | ~$1.94–6/mo for shared-cpu-1x/256MB, + $0.15/GB/mo per volume even when stopped | Yes — `auto_stop_machines`; set `min_machines_running=1` to force always-on | 1–3s microVM resume + import cost | Only with explicit `min_machines_running=1`; **no built-in session affinity** | Yes while running — but auto-stop can kill a task mid-flight unless disabled | No hard platform timeout | `flyctl deploy` (not git-push), Dockerfile required, `fly secrets set` |
| **Modal** | $30/mo free credit — effectively free at this traffic | Pay-per-second; `min_containers=1` bills continuously | Yes by default; `min_containers=1` reduces but doesn't eliminate | <5s generic, plus heavy LangChain imports | Awkward — needs `min_containers=1` **and** `max_containers=1`, fighting the model | Native fit for auto mode (`.spawn()` job queue); poor fit for HITL's in-RAM dict | Web endpoints hard-capped at **150s** | `modal deploy`, image defined in Python, no Dockerfile |
| **Cloud Run** | Yes — 2M req/mo, 360k GB-s, 180k vCPU-s, forever | `min-instances=1` memory-only ≈ a few $/mo; **with `--no-cpu-throttling` ≈ $10–65/mo** depending on sizing | Yes by default; disable via `min-instances≥1` | Non-issue once `min-instances=1` | Yes — `min-instances=1` **and** `max-instances=1` (stronger than the best-effort affinity cookie) | **No by default** — CPU throttled to zero the instant the response is sent; needs `--no-cpu-throttling` | Up to 60 min (default 5) | `gcloud run deploy`, buildpacks or Dockerfile, Secret Manager |

## The `interrupt()` + MemorySaver constraint

`MemorySaver` is a plain in-process dict — no persistence, no cross-process visibility. Two failure modes follow directly:

**A. Scale-to-zero between `/hitl/start` and `/hitl/resume`.** A reviewer reads a draft for several minutes; the platform idles the instance down; the dict dies with the process. The resume finds no checkpoint. This app returns a clean `404 "Unknown or expired thread_id"` for that case rather than a stack trace, but the session is still lost. This is Render's free tier and Cloud Run's default behaviour.

**B. Two or more instances, resume hits the wrong one.** `/hitl/start` writes the checkpoint into instance A's RAM; `/hitl/resume` round-robins to instance B, which has never heard of that `thread_id`. Same 404, no idling required. Any horizontal scale — including rolling-deploy overlap — triggers it.

Making the in-memory pattern safe, per platform:

- **Railway** — leave replicas at the default 1, turn off App Sleeping. No min-instances knob needed.
- **Render** — safe on Starter by construction. Not safe on free.
- **Fly.io** — `min_machines_running=1` in `fly.toml`, one machine.
- **Cloud Run** — needs **both** `--min-instances=1` and `--max-instances=1`. Session affinity alone is documented as best-effort and breaks on instance termination.
- **Modal** — the one platform where pinning isn't idiomatic. Not recommended for the HITL half.

The change that removes the constraint entirely is swapping `MemorySaver` for `SqliteSaver` (`langgraph-checkpoint-sqlite`, needs a writable persistent path) or `PostgresSaver` (`langgraph-checkpoint-postgres`, e.g. free-tier Neon). **This is deliberately not done here** — MemorySaver is the right call for a zero-traffic demo. The point of naming it is that MemorySaver is what forces "exactly one always-on instance" onto the hosting decision. At a handful of clicks a week that guarantee is trivial and cheap on four of the five platforms, so the constraint is a reason to pick an easy platform, not a reason to add a database.

## Recommendation

**Railway Hobby, App Sleeping off, default single replica.**

It is the only option here where "one always-on process" is both the default (autoscaling is opt-in) and cheap to guarantee — one toggle, versus Cloud Run's `min-instances`/`max-instances`/`--no-cpu-throttling` trio or Fly's `fly.toml` lifecycle tuning. Because it's a real persistent container, the auto-mode background task just runs, with no CPU-freeze to configure around. Git-push deploys with Nixpacks auto-detecting Python; API keys are a dashboard field. Roughly $5–10/mo.

**Runner-up: Render Starter ($7/mo flat).** Functionally near-identical for this workload. Switch to it if Railway's metered billing on top of the $5 floor feels like unpredictable-bill risk — Render's flat $7 is the cleaner mental model for something nobody actively operates.

Not Fly.io despite being cheapest: it's the only one requiring a Dockerfile, CLI secrets, and machine-lifecycle tuning for the same guarantee. Not Cloud Run: making it safe for *both* of this app's constraints stacks three flags and pushes real cost to $10–65/mo, so the generous free tier doesn't actually apply. Not Modal, unless the app were autonomous-mode-only — its job-queue pattern is a genuinely good fit for auto mode and a bad fit for HITL.

## Gotchas

- **Sleep-on-idle is the biggest live-demo risk.** A recruiter clicks your link after a quiet weekend and waits 30s–3min on a blank screen. Treat always-on as the one non-negotiable spend.
- **Deploy restarts drop in-flight HITL sessions** on every platform, `min-instances` or not. Not worth engineering around at this traffic, but don't push while demoing.
- **Bind to `0.0.0.0:$PORT`** and point health checks at `/api/health` — it deliberately does not call Mistral, so a slow provider can't flap your instance.
- **Build size**: the LangChain/LangGraph/Mistral dependency tree is sizeable. Affects deploy time more than runtime once pinned always-on, but it compounds badly with any scale-to-zero setup.

## Sources

[Railway free tier 2026](https://medium.com/@kuberns/railway-free-tier-in-2026-what-you-get-and-when-it-runs-out-2101fdca0998) · [Railway pricing](https://costbench.com/software/developer-tools/railway/) · [Railway app sleeping](https://docs.railway.com/reference/app-sleeping) · [Railway scaling](https://docs.railway.com/deployments/scaling) · [Railpack](https://blog.railway.com/p/introducing-railpack) · [Render 2026 pricing](https://agentdeals.dev/vendor/render) · [Render Starter pricing](https://kuberns.com/blogs/render-pricing/) · [Render cold starts](https://blog.samkiel.dev/your-render-free-tier-is-not-broken-its-just-cold) · [Fly.io free tier ended](https://expresstech.io/7-fly-io-alternatives-in-2026-real-pricing-after-the-free-tier-died/) · [Fly.io pricing](https://fly.io/docs/about/pricing/) · [Fly.io sticky sessions](https://fly.io/docs/blueprints/sticky-sessions/) · [Modal pricing](https://makerstack.co/reviews/modal-review/) · [Modal cold start](https://modal.com/docs/guide/cold-start) · [Modal job queue](https://modal.com/docs/guide/job-queue) · [Modal webhook timeouts](https://modal.com/docs/guide/webhook-timeouts) · [Cloud Run pricing](https://cloud.google.com/run/pricing) · [Cloud Run CPU always-on](https://oneuptime.com/blog/post/2026-02-17-how-to-configure-cloud-run-cpu-allocation-to-always-on-for-background-processing-workloads/view) · [Cloud Run session affinity](https://docs.cloud.google.com/run/docs/configuring/session-affinity) · [Cloud Run WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets)
