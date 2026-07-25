import { useCallback, useRef, useState } from "react";
import {
  APPROVAL_TOKEN,
  hitlResume,
  hitlStart,
  toApiError,
  type ApiError,
  type HitlResponse,
  type StopReason,
} from "../lib/api";

/** A round the human sent back for a rewrite, kept so the transcript reads as a conversation. */
export interface HitlRound {
  attempt: number;
  draft: string;
  feedback: string;
}

export type HitlPhase =
  | "idle"
  /** Waiting on the writer for the very first draft. */
  | "drafting"
  /** The graph is suspended on interrupt(). Nothing moves until the human acts. */
  | "awaiting_review"
  /** The human's verdict is in flight; the writer is rewriting. */
  | "revising"
  | "completed"
  /** Terminal: no draft to fall back to, or the session can no longer be resumed. */
  | "failed";

export interface HitlState {
  threadId: string | null;
  phase: HitlPhase;
  draft: string | null;
  attempt: number;
  instruction: string | null;
  rounds: HitlRound[];
  isApproved: boolean | null;
  stopReason: StopReason | null;
  error: ApiError | null;
  /** What the user last tried to send, so a failed submit can be retried verbatim. */
  lastFeedback: string | null;
}

const IDLE: HitlState = {
  threadId: null,
  phase: "idle",
  draft: null,
  attempt: 0,
  instruction: null,
  rounds: [],
  isApproved: null,
  stopReason: null,
  error: null,
  lastFeedback: null,
};

function applyResponse(
  prev: HitlState,
  res: HitlResponse,
  sentFeedback: string | null,
): HitlState {
  // A rejected round only becomes history once the server confirms it moved on
  // to a new attempt. Recording it optimistically would leave a phantom round
  // behind whenever the resume call failed.
  const rounds =
    prev.draft !== null && sentFeedback !== null && res.attempt > prev.attempt
      ? [...prev.rounds, { attempt: prev.attempt, draft: prev.draft, feedback: sentFeedback }]
      : prev.rounds;

  const base = {
    ...prev,
    threadId: res.thread_id,
    draft: res.draft,
    attempt: res.attempt,
    rounds,
    error: null,
    lastFeedback: null,
  };

  if (res.status === "completed") {
    return {
      ...base,
      phase: "completed",
      instruction: null,
      isApproved: res.is_approved ?? null,
      stopReason: res.stop_reason ?? null,
    };
  }

  return {
    ...base,
    phase: "awaiting_review",
    instruction: res.instruction ?? null,
  };
}

/**
 * The human-gated loop: start, then resume for as long as the server keeps
 * saying `awaiting_review`. It never polls — there is nothing to poll for. The
 * graph is parked on the server until this client sends a verdict.
 */
export function useHitlSession() {
  const [state, setState] = useState<HitlState>(IDLE);
  // Reading the id from state inside the callback would capture whatever value
  // was current when the callback was built; a ref always has the latest.
  const threadIdRef = useRef<string | null>(null);
  const inFlight = useRef(false);

  const reset = useCallback(() => {
    threadIdRef.current = null;
    inFlight.current = false;
    setState(IDLE);
  }, []);

  const start = useCallback(async (topic: string, enableSearch: boolean) => {
    if (inFlight.current) return;
    inFlight.current = true;
    threadIdRef.current = null;
    setState({ ...IDLE, phase: "drafting" });

    try {
      const res = await hitlStart(topic, enableSearch);
      threadIdRef.current = res.thread_id;
      setState((prev) => applyResponse(prev, res, null));
    } catch (err) {
      // The old build dropped back to `idle` here, which the page treated as
      // "nothing has happened yet" and rendered nothing at all. A failed start
      // has to stay on screen.
      setState({ ...IDLE, phase: "failed", error: toApiError(err) });
    } finally {
      inFlight.current = false;
    }
  }, []);

  const submit = useCallback(async (feedback: string) => {
    const threadId = threadIdRef.current;
    if (!threadId || inFlight.current) return;
    inFlight.current = true;

    setState((prev) => ({ ...prev, phase: "revising", error: null, lastFeedback: feedback }));

    try {
      const res = await hitlResume(threadId, feedback);
      setState((prev) => applyResponse(prev, res, feedback));
    } catch (err) {
      const error = toApiError(err);
      setState((prev) => ({
        ...prev,
        // A 404 means the server no longer holds this thread, so there is no
        // verdict left to cast — the draft on screen is a dead end. Anything
        // else is worth retrying against the same thread.
        phase: error.isExpiredSession ? "failed" : "awaiting_review",
        error,
      }));
    } finally {
      inFlight.current = false;
    }
  }, []);

  const approve = useCallback(() => submit(APPROVAL_TOKEN), [submit]);

  const retryLast = useCallback(() => {
    const pending = state.lastFeedback;
    if (pending) void submit(pending);
  }, [state.lastFeedback, submit]);

  return { state, start, submit, approve, retryLast, reset };
}
