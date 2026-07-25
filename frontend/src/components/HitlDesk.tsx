import { useState } from "react";
import { readsAsApproval } from "../lib/api";
import type { HitlRound, HitlState } from "../hooks/useHitlSession";
import { ErrorBanner } from "./ErrorBanner";
import { FinalPost } from "./FinalPost";

interface Props {
  state: HitlState;
  maxAttempts: number;
  onApprove: () => void;
  onFeedback: (text: string) => void;
  onRetry: () => void;
  onReset: () => void;
}

/**
 * The human mode is a conversation with pauses, so it is laid out like one: the
 * manuscript on the left, the editor's response pad on the right, and every
 * round that came before stacked above as a transcript.
 *
 * It deliberately shows no spinner while it waits. Nothing is running — the
 * graph is suspended on `interrupt()` and will stay that way indefinitely. A
 * spinner would claim otherwise.
 */
export function HitlDesk({
  state,
  maxAttempts,
  onApprove,
  onFeedback,
  onRetry,
  onReset,
}: Props) {
  const { phase, draft, attempt, rounds, error } = state;

  if (phase === "drafting") {
    return (
      <div className="py-24 text-center">
        <p className="font-serif text-3xl text-ink-soft sm:text-4xl">
          Setting the first draft
          <span className="ml-1 inline-block animate-blink text-accent" aria-hidden="true">
            ▌
          </span>
        </p>
        <p className="label mt-5 text-ink-faint">Then it stops and waits for you</p>
        <span role="status" className="sr-only">
          Writing the first draft.
        </span>
      </div>
    );
  }

  if (phase === "failed" && !draft) {
    return error ? <ErrorBanner error={error} onReset={onReset} /> : null;
  }

  if (phase === "completed" && draft) {
    return (
      <div className="space-y-10">
        {rounds.length > 0 && <Transcript rounds={rounds} />}
        <FinalPost
          draft={draft}
          attempt={attempt}
          maxAttempts={maxAttempts}
          stopReason={state.stopReason}
          isApproved={state.isApproved}
          judge="you"
          onReset={onReset}
        />
      </div>
    );
  }

  if (!draft) return null;

  const revising = phase === "revising";
  const dead = phase === "failed";

  return (
    <div className="space-y-10">
      {rounds.length > 0 && <Transcript rounds={rounds} />}

      {error && (
        <ErrorBanner
          error={error}
          onRetry={dead ? undefined : onRetry}
          retryLabel="Send it again"
          onReset={onReset}
        />
      )}

      <div className="grid grid-cols-1 gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <article>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-3">
            <h2 className="label text-ink-faint">
              Draft — attempt {attempt} of {maxAttempts}
            </h2>
            <span className="label flex items-center gap-2 text-accent">
              {revising ? (
                <>
                  <span className="size-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true" />
                  Rewriting on your note
                </>
              ) : dead ? (
                <>
                  <span className="size-1.5 rounded-full bg-bad" aria-hidden="true" />
                  <span className="text-bad">Session ended</span>
                </>
              ) : (
                <>
                  {/* Square, not a dot, and it does not pulse: nothing is running. */}
                  <span className="size-1.5 bg-accent" aria-hidden="true" />
                  Graph suspended
                </>
              )}
            </span>
          </div>

          <div
            className={
              "draft-body max-w-[64ch] text-[1.3rem] text-ink transition-opacity sm:text-2xl " +
              (revising ? "opacity-40" : "")
            }
          >
            {draft}
          </div>
        </article>

        <VerdictRail
          instruction={state.instruction}
          attempt={attempt}
          maxAttempts={maxAttempts}
          busy={revising}
          disabled={dead}
          onApprove={onApprove}
          onFeedback={onFeedback}
        />
      </div>
    </div>
  );
}

function VerdictRail({
  instruction,
  attempt,
  maxAttempts,
  busy,
  disabled,
  onApprove,
  onFeedback,
}: {
  instruction: string | null;
  attempt: number;
  maxAttempts: number;
  busy: boolean;
  disabled: boolean;
  onApprove: () => void;
  onFeedback: (text: string) => void;
}) {
  const [text, setText] = useState("");

  // The backend's loop router ends the run when a rejection lands on the last
  // attempt — it does not rewrite once more. So on the final round, sending a
  // note is not "revise", it is "stop without approving", and the button says so.
  const lastRound = attempt >= maxAttempts;
  const roundsLeft = Math.max(0, maxAttempts - attempt);
  const trimmed = text.trim();
  const ambiguous = readsAsApproval(trimmed);
  const canSend = trimmed.length > 0 && !busy && !disabled;

  const send = () => {
    if (!canSend) return;
    onFeedback(trimmed);
    setText("");
  };

  return (
    <aside className="lg:sticky lg:top-6 lg:self-start">
      <div className="rounded-lg border border-rule bg-surface p-5">
        <h3 className="label text-ink-faint">Your verdict</h3>
        <p className="mt-2 text-xs leading-relaxed text-ink-soft">
          The run is parked on the server. It resumes only when you answer.
        </p>

        <button
          type="button"
          onClick={onApprove}
          disabled={busy || disabled}
          className="label mt-4 w-full rounded-md border border-ok/40 bg-ok-wash py-3 text-ok transition-colors hover:bg-ok/15 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Sending…" : "Approve — ship it"}
        </button>

        <div className="my-4 flex items-center gap-3" aria-hidden="true">
          <span className="h-px flex-1 bg-rule" />
          <span className="label text-ink-faint">or</span>
          <span className="h-px flex-1 bg-rule" />
        </div>

        <label htmlFor="hitl-feedback" className="label text-ink-faint">
          Tell it what to change
        </label>
        <textarea
          id="hitl-feedback"
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, 4000))}
          disabled={busy || disabled}
          rows={5}
          placeholder="Cut the hashtags and open with the number, not the anecdote."
          aria-describedby="hitl-feedback-note"
          className="mt-2 w-full resize-y rounded-md border border-rule bg-paper px-3 py-2.5 text-sm leading-relaxed text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none disabled:opacity-60"
        />

        {ambiguous && (
          <p className="mt-2 text-xs leading-relaxed text-warn">
            The backend reads “{trimmed}” on its own as approval, not as a note. Use
            the Approve button if that is what you meant.
          </p>
        )}

        <button
          type="button"
          onClick={send}
          disabled={!canSend}
          className="label mt-3 w-full rounded-md bg-accent py-3 text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-35"
        >
          {busy ? "Sending…" : lastRound ? "End without approving" : "Send for rewrite"}
        </button>

        <p id="hitl-feedback-note" className="mt-3 text-xs leading-relaxed text-ink-faint">
          {disabled
            ? "This session can no longer be resumed. Start over to open a new one."
            : lastRound
            ? `Attempt ${maxAttempts} of ${maxAttempts} is the ceiling. Sending a note now ends the run with this draft instead of rewriting it.`
            : `${roundsLeft} rewrite${roundsLeft === 1 ? "" : "s"} left before the attempt cap.`}
        </p>
      </div>

      {instruction && (
        <p className="mt-4 border-l-2 border-rule pl-4 font-serif text-sm italic leading-relaxed text-ink-faint">
          {instruction}
        </p>
      )}
    </aside>
  );
}

function Transcript({ rounds }: { rounds: HitlRound[] }) {
  return (
    <section aria-label="Earlier rounds" className="space-y-3">
      <h2 className="label text-ink-faint">Earlier rounds</h2>
      {rounds.map((round) => (
        <details
          key={round.attempt}
          className="group rounded-lg border border-rule bg-sunk px-5 py-4"
        >
          <summary className="flex cursor-pointer flex-wrap items-baseline justify-between gap-x-4 gap-y-1 list-none">
            <span className="label text-ink-faint">
              Attempt {round.attempt} — you sent it back
            </span>
            <span className="label text-accent group-open:hidden">Show</span>
            <span className="label hidden text-accent group-open:inline">Hide</span>
          </summary>
          <div className="mt-4 space-y-4">
            <div className="draft-body max-w-[64ch] text-base text-ink-soft">
              {round.draft}
            </div>
            <div className="border-l-2 border-accent pl-4">
              <p className="label text-accent">Your note</p>
              <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-ink-soft break-words">
                {round.feedback}
              </p>
            </div>
          </div>
        </details>
      ))}
    </section>
  );
}
