"""CLI for the human-in-the-loop pipeline.

Replaces Human_in_the_Loop.py. All graph logic now lives in app/ so the same
code backs both this CLI and the API — nothing here runs at import time.
"""

import sys

from langgraph.types import Command

from app import config, jobs
from app.graph_hitl import app_hitl
from app.state import initial_state
from app.writer import stop_reason

RULE = "=" * 55


def main() -> int:
    config.configure_logging()

    print(RULE)
    print("LinkedIn Post Generator — Human-in-the-Loop")
    print(RULE)
    print("\nDrafts a post, shows it to YOU, and rewrites on your feedback.")
    print(RULE)

    topic = input("\nWhat topic do you want a LinkedIn post about?\n> ").strip()
    if not topic:
        print("\nNo topic given. Exiting.")
        return 1

    use_search = input("Use web search? [y/N] ").strip().lower().startswith("y")

    # A fresh id per run, so two runs never share a checkpoint.
    thread_id = jobs.create_session(topic, use_search)
    graph_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": config.GRAPH_RECURSION_LIMIT,
    }

    print(f"\nSession {thread_id}\nStarting generation...\n")

    result = app_hitl.invoke(initial_state(topic, use_search), config=graph_config)

    while result.get("__interrupt__"):
        payload = result["__interrupt__"][0].value

        print("\n" + RULE)
        print(f"DRAFT FOR YOUR REVIEW (attempt {payload['attempt']}/{config.MAX_ATTEMPTS})")
        print(RULE)
        print(payload["draft"])
        print(RULE)
        print(f"\n{payload['instruction']}")

        response = input("\nYour response: ").strip()
        if not response:
            print("Empty response — treating as a request to keep the draft.")
            response = "approved"

        result = app_hitl.invoke(Command(resume=response), config=graph_config)

    if result.get("error"):
        print(f"\nFailed: {result['error']}")
        return 1

    print("\n" + RULE)
    print("FINAL LINKEDIN POST")
    print(RULE)
    print(result["draft"])
    print(RULE)
    print(f"Attempts: {result['attempt']}")
    print(f"Approved by human: {result['is_approved']}")
    print(f"Stopped because: {stop_reason(result)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
