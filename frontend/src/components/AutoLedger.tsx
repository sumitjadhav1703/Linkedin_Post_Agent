import { useMemo } from "react";
import type { AutoHistoryEntry } from "../lib/api";
import type { AutoState } from "../hooks/useAutoSession";
import { useElapsed } from "../hooks/useElapsed";
import { ErrorBanner } from "./ErrorBanner";
import { FinalPost } from "./FinalPost";

interface Props {
  state: AutoState;
  maxAttempts: number;
  onResumePolling: () => void;
  onReset: () => void;
}

const clock = (seconds: number) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

/**
 * The autonomous mode is a machine grinding, and it is laid out as a ledger
 * rather than a conversation: one spine, one row per attempt, appended in place
 * as the poll picks up new history. Rejected drafts stay on screen with the
 * critique that killed them — watching a draft get torn up and come back better
 * is the part worth showing.
 *
 * `.machine` shifts the palette cool for this whole subtree, so the mode reads
 * as a different room from the warm human desk.
 */
export function AutoLedger({ state, maxAttempts, onResumePolling, onReset }: Props) {
  const { phase, history, attempt, draft, error } = state;
  const running = phase === "running" || phase === "starting";
  const elapsed = useElapsed(state.startedAt, running);

  const announcement = useMemo(() => describe(state), [state]);

  const last = history.at(-1);
  const awaitingRewrite = running && last?.approved === false;
  const awaitingFirstDraft = running && history.length === 0;

  return (
    // The cool palette only reads as a different room if it owns a surface —
    // without one, the warm page shows through and only the borders shift.
    <div className="machine dot-grid -mx-4 space-y-8 rounded-lg border border-rule bg-paper p-4 sm:-mx-6 sm:p-6">
      <Telemetry
        phase={phase}
        elapsed={elapsed}
        attempt={attempt}
        maxAttempts={maxAttempts}
        polls={state.polls}
      />

      {/* Concise announcements, rather than aria-live on the timeline itself —
          which would re-read every draft on screen on each 1.5s poll. */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {error && (
        <ErrorBanner
          error={error}
          onRetry={error.isExpiredSession || !state.jobId ? undefined : onResumePolling}
          retryLabel="Resume watching"
          onReset={onReset}
        />
      )}

      {(history.length > 0 || running) && (
        <ol className="relative space-y-4 border-l border-rule pl-6 sm:pl-8">
          {history.map((entry) => (
            <Row key={entry.attempt} entry={entry} />
          ))}
          {awaitingFirstDraft && <PendingRow attempt={1} label="Writer drafting" />}
          {awaitingRewrite && (
            <PendingRow attempt={last.attempt + 1} label="Writer rewriting on the critique" />
          )}
        </ol>
      )}

      {phase === "completed" && draft && (
        <FinalPost
          draft={draft}
          attempt={attempt}
          maxAttempts={maxAttempts}
          stopReason={state.stopReason}
          isApproved={state.isApproved}
          judge="reviewer"
          onReset={onReset}
        />
      )}
    </div>
  );
}

function Telemetry({
  phase,
  elapsed,
  attempt,
  maxAttempts,
  polls,
}: {
  phase: AutoState["phase"];
  elapsed: number;
  attempt: number;
  maxAttempts: number;
  polls: number;
}) {
  const running = phase === "running" || phase === "starting";

  return (
    <div className="overflow-hidden rounded-md border border-rule bg-surface">
      <dl className="flex flex-wrap items-baseline gap-x-8 gap-y-2 px-5 py-3">
        <Field label="Status">
          <span
            className={
              running ? "text-accent" : phase === "error" ? "text-bad" : "text-ok"
            }
          >
            {running ? "running" : phase}
          </span>
        </Field>
        <Field label="Elapsed">{clock(elapsed)}</Field>
        <Field label="Attempt">
          {attempt || "—"} / {maxAttempts}
        </Field>
        {/* Also the honest answer to "did polling actually stop?" — it freezes. */}
        <Field label="Polls">{polls}</Field>
      </dl>
      <div className="h-0.5 w-full overflow-hidden bg-rule" aria-hidden="true">
        {running && <div className="h-full w-1/4 animate-sweep bg-accent" />}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="label text-ink-faint">{label}</dt>
      <dd className="font-mono text-xs tabular-nums text-ink">{children}</dd>
    </div>
  );
}

function Marker({ tone }: { tone: string }) {
  return (
    <span
      aria-hidden="true"
      className={`absolute top-6 -left-[calc(1.5rem+4.5px)] size-2 rounded-full ring-4 ring-paper sm:-left-[calc(2rem+4.5px)] ${tone}`}
    />
  );
}

function Row({ entry }: { entry: AutoHistoryEntry }) {
  const ruling = entry.approved === null;
  const rejected = entry.approved === false;

  const tone = ruling ? "bg-accent" : rejected ? "bg-bad" : "bg-ok";
  const verdict = ruling
    ? { text: "Reviewer ruling", cls: "text-accent" }
    : rejected
      ? { text: "Rejected", cls: "text-bad" }
      : { text: "Approved", cls: "text-ok" };

  return (
    <li
      className={
        "relative animate-rise rounded-lg border border-rule bg-surface px-5 py-5 sm:px-6 " +
        (rejected ? "opacity-75" : "")
      }
    >
      <Marker tone={tone} />

      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="label text-ink-faint">
          Attempt {String(entry.attempt).padStart(2, "0")}
        </span>
        <span className={`label flex items-center gap-2 ${verdict.cls}`}>
          {ruling && (
            <span className="flex gap-0.5" aria-hidden="true">
              <span className="size-1 animate-bounce rounded-full bg-accent" />
              <span className="size-1 animate-bounce rounded-full bg-accent [animation-delay:0.15s]" />
              <span className="size-1 animate-bounce rounded-full bg-accent [animation-delay:0.3s]" />
            </span>
          )}
          {verdict.text}
        </span>
      </div>

      <div className="draft-body max-w-[62ch] text-lg text-ink sm:text-xl">
        {entry.draft}
      </div>

      {rejected && entry.feedback && (
        <div className="mt-5 border-l-2 border-bad bg-bad-wash py-3 pr-4 pl-4">
          <p className="label text-bad">Reviewer critique</p>
          <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-ink-soft break-words">
            {entry.feedback}
          </p>
        </div>
      )}
    </li>
  );
}

function PendingRow({ attempt, label }: { attempt: number; label: string }) {
  return (
    <li className="relative animate-rise rounded-lg border border-dashed border-rule-strong px-5 py-5 sm:px-6">
      <Marker tone="bg-accent" />
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <span className="label text-ink-faint">
          Attempt {String(attempt).padStart(2, "0")}
        </span>
        <span className="label flex items-center gap-2 text-accent">
          <span className="flex gap-0.5" aria-hidden="true">
            <span className="size-1 animate-bounce rounded-full bg-accent" />
            <span className="size-1 animate-bounce rounded-full bg-accent [animation-delay:0.15s]" />
            <span className="size-1 animate-bounce rounded-full bg-accent [animation-delay:0.3s]" />
          </span>
          {label}
        </span>
      </div>
    </li>
  );
}

/** One sentence per meaningful change, for the live region. */
function describe(state: AutoState): string {
  const last = state.history.at(-1);

  switch (state.phase) {
    case "starting":
      return "Starting the autonomous run.";
    case "running":
      if (!last) return "The writer is drafting attempt 1.";
      if (last.approved === null)
        return `Attempt ${last.attempt} drafted. The reviewer is deciding.`;
      if (last.approved === false)
        return `Attempt ${last.attempt} was rejected. The writer is rewriting.`;
      return `Attempt ${last.attempt} was approved.`;
    case "completed":
      return state.stopReason === "approved"
        ? `Finished. The reviewer approved attempt ${state.attempt}.`
        : `Finished without approval after ${state.attempt} attempts.`;
    case "error":
      return `The run stopped: ${state.error?.detail ?? "unknown error"}`;
    default:
      return "";
  }
}
