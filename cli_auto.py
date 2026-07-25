"""CLI for the autonomous pipeline.

Replaces Iterative_Tools.py. Same writer as the human-in-the-loop CLI; the only
difference is that an LLM casts the verdict instead of you.
"""

import sys

from app import config
from app.graph_auto import app_auto
from app.state import initial_state
from app.writer import WRITER_ENTRY_NODE, WRITER_EXIT_NODE, stop_reason

RULE = "=" * 55


def main() -> int:
    config.configure_logging()

    print(RULE)
    print("LinkedIn Post Generator — Autonomous")
    print(RULE)
    print("\nDrafts a post, reviews it itself, and iterates until publish-ready.")
    print(RULE)

    topic = input("\nWhat topic do you want a LinkedIn post about?\n> ").strip()
    if not topic:
        print("\nNo topic given. Exiting.")
        return 1

    use_search = input("Use web search? [y/N] ").strip().lower().startswith("y")

    print("\nStarting generation...\n")

    attempt = 0
    final: dict = {}

    for chunk in app_auto.stream(
        initial_state(topic, use_search),
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
                print(f"\n--- Draft {attempt}/{config.MAX_ATTEMPTS} ---")
                print(update["draft"])
            elif node == "reviewer" and "is_approved" in update:
                verdict = "APPROVED" if update["is_approved"] else "REJECTED"
                print(f"\n[Reviewer: {verdict}] {update.get('review_feedback', '')}")

    if final.get("error"):
        print(f"\nFailed: {final['error']}")
        return 1

    print("\n" + RULE)
    print("FINAL LINKEDIN POST")
    print(RULE)
    print(final.get("draft", ""))
    print(RULE)
    print(f"Attempts: {final.get('attempt', attempt)}")
    print(f"Approved: {bool(final.get('is_approved'))}")
    print(f"Stopped because: {stop_reason(final)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
