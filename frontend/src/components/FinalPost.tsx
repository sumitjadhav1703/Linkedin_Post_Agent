import type { StopReason } from "../lib/api";
import { CopyButton } from "./CopyButton";

interface Props {
  draft: string;
  attempt: number;
  maxAttempts: number;
  stopReason: StopReason | null;
  isApproved: boolean | null;
  judge: "you" | "reviewer";
  onReset: () => void;
}

/**
 * "It passed" and "we ran out of tries" both end the graph, and both leave a
 * draft on screen. They are not the same result, so they do not get the same
 * treatment — the second one says outright that nothing approved this text.
 */
export function FinalPost({
  draft,
  attempt,
  maxAttempts,
  stopReason,
  isApproved,
  judge,
  onReset,
}: Props) {
  const approved = stopReason === "approved" || isApproved === true;

  const heading = approved
    ? judge === "you"
      ? "You approved this"
      : "The reviewer model approved this"
    : "Never approved";

  const note = approved
    ? `Passed on attempt ${attempt} of ${maxAttempts}.`
    : judge === "you"
      ? `The loop hit its ceiling of ${maxAttempts} attempts. This is the last draft the writer produced — you never signed off on it.`
      : `The reviewer rejected every attempt and the loop hit its ceiling of ${maxAttempts}. This is the last draft the writer produced, not one that passed review.`;

  return (
    <section
      aria-labelledby="final-heading"
      className={
        "overflow-hidden rounded-lg border bg-surface " +
        (approved ? "border-ok/40" : "border-warn/50")
      }
    >
      <div
        className={
          "flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b px-6 py-4 sm:px-10 " +
          (approved ? "border-ok/25 bg-ok-wash" : "border-warn/25 bg-warn-wash")
        }
      >
        <h2
          id="final-heading"
          className={"label " + (approved ? "text-ok" : "text-warn")}
        >
          {heading}
        </h2>
        <p className="max-w-prose text-xs leading-relaxed text-ink-soft">{note}</p>
      </div>

      <article className="draft-body px-6 py-9 text-[1.35rem] text-ink sm:px-10 sm:py-12 sm:text-2xl">
        {draft}
      </article>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule bg-sunk px-6 py-4 sm:px-10">
        <CopyButton text={draft} />
        <button
          type="button"
          onClick={onReset}
          className="label rounded border border-rule px-3 py-1.5 text-ink-soft transition-colors hover:border-rule-strong hover:text-ink"
        >
          New topic
        </button>
      </div>
    </section>
  );
}
