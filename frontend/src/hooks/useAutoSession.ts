import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  autoStart,
  autoStatus,
  toApiError,
  type AutoHistoryEntry,
  type StopReason,
} from "../lib/api";

const POLL_MS = 1500;
/** One dropped poll on a flaky connection should not kill a run that is still going. */
const MAX_CONSECUTIVE_POLL_FAILURES = 3;

export type AutoPhase = "idle" | "starting" | "running" | "completed" | "error";

export interface AutoState {
  jobId: string | null;
  phase: AutoPhase;
  attempt: number;
  history: AutoHistoryEntry[];
  draft: string | null;
  isApproved: boolean | null;
  stopReason: StopReason | null;
  error: ApiError | null;
  startedAt: number | null;
  /** Successful status requests this run. Surfaced in the UI as run telemetry. */
  polls: number;
}

const IDLE: AutoState = {
  jobId: null,
  phase: "idle",
  attempt: 0,
  history: [],
  draft: null,
  isApproved: null,
  stopReason: null,
  error: null,
  startedAt: null,
  polls: 0,
};

/**
 * The autonomous loop: kick it off, then watch. The job runs to completion on
 * the server whether or not anyone is looking, so this is a read loop, not a
 * conversation — and `history` growing between polls is the whole show.
 */
export function useAutoSession() {
  const [state, setState] = useState<AutoState>(IDLE);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const failures = useRef(0);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  // Covers navigation away, mode switches that unmount this tree, and hot reloads.
  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback(
    async (jobId: string) => {
      try {
        const res = await autoStatus(jobId);
        failures.current = 0;

        setState((prev) => ({
          ...prev,
          jobId: res.job_id,
          phase: res.status,
          attempt: res.attempt,
          history: res.history,
          draft: res.draft,
          isApproved: res.is_approved,
          stopReason: res.stop_reason,
          // A job that failed server-side reports it in the payload, not the
          // status code — the poll itself succeeded.
          error: res.error ? new ApiError(502, res.error) : null,
          polls: prev.polls + 1,
        }));

        if (res.status !== "running") stopPolling();
      } catch (err) {
        const error = toApiError(err);

        // The job is gone from the server's memory; no amount of retrying finds
        // it again. Everything else gets a few chances before giving up.
        const fatal =
          error.isExpiredSession || ++failures.current >= MAX_CONSECUTIVE_POLL_FAILURES;

        if (fatal) {
          stopPolling();
          setState((prev) => ({ ...prev, phase: "error", error }));
        }
      }
    },
    [stopPolling],
  );

  const beginPolling = useCallback(
    (jobId: string) => {
      stopPolling();
      failures.current = 0;
      void poll(jobId);
      timer.current = setInterval(() => void poll(jobId), POLL_MS);
    },
    [poll, stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    failures.current = 0;
    setState(IDLE);
  }, [stopPolling]);

  const start = useCallback(
    async (topic: string, enableSearch: boolean) => {
      stopPolling();
      failures.current = 0;
      setState({ ...IDLE, phase: "starting", startedAt: Date.now() });

      try {
        const res = await autoStart(topic, enableSearch);
        setState((prev) => ({ ...prev, jobId: res.job_id, phase: "running" }));
        beginPolling(res.job_id);
      } catch (err) {
        setState({ ...IDLE, phase: "error", error: toApiError(err) });
      }
    },
    [beginPolling, stopPolling],
  );

  /** After a transient network failure: the job may well still be running. */
  const resumePolling = useCallback(() => {
    const jobId = state.jobId;
    if (!jobId) return;
    setState((prev) => ({ ...prev, phase: "running", error: null }));
    beginPolling(jobId);
  }, [beginPolling, state.jobId]);

  return { state, start, reset, resumePolling };
}
