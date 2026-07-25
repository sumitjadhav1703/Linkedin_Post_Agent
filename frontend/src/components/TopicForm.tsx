import { useId, useState } from "react";
import type { Mode } from "./ModeToggle";

const MAX_TOPIC = 500; // matches the backend's Field(max_length=500)

interface Props {
  mode: Mode;
  onSubmit: (topic: string, enableSearch: boolean) => void;
  busy: boolean;
  locked: boolean;
  searchAvailable: boolean;
}

const COPY: Record<Mode, { cta: string; busy: string; hint: string }> = {
  hitl: {
    cta: "Write a first draft",
    busy: "Drafting…",
    hint: "It will stop after the draft and wait for you.",
  },
  auto: {
    cta: "Run the loop",
    busy: "Starting…",
    hint: "It will run to a verdict on its own. Usually 15–45 seconds.",
  },
};

export function TopicForm({ mode, onSubmit, busy, locked, searchAvailable }: Props) {
  const [topic, setTopic] = useState("");
  const [search, setSearch] = useState(false);
  const [touched, setTouched] = useState(false);

  const id = useId();
  const trimmed = topic.trim();
  // Caught here so a blank topic never becomes a 400 round-trip.
  const blank = trimmed.length === 0;
  const showError = touched && blank;
  const copy = COPY[mode];

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (blank || busy || locked) return;
    onSubmit(trimmed, search && searchAvailable);
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor={`${id}-topic`} className="label text-ink-faint">
          Topic
        </label>
        <textarea
          id={`${id}-topic`}
          value={topic}
          onChange={(e) => setTopic(e.target.value.slice(0, MAX_TOPIC))}
          onBlur={() => setTouched(true)}
          disabled={locked}
          rows={2}
          aria-invalid={showError}
          aria-describedby={`${id}-status`}
          placeholder="What burnout actually costs an engineering team"
          className="mt-2 w-full resize-y rounded-md border border-rule bg-surface px-4 py-3 font-serif text-xl leading-snug text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none disabled:opacity-60"
        />
        <div
          id={`${id}-status`}
          className="mt-2 flex flex-wrap items-center justify-between gap-3"
        >
          <span className={"label " + (showError ? "text-bad" : "text-ink-faint")}>
            {showError ? "Enter a topic first" : `${topic.length} / ${MAX_TOPIC}`}
          </span>

          <label
            className={
              "flex items-center gap-2.5 " +
              (searchAvailable && !locked ? "cursor-pointer" : "cursor-not-allowed opacity-55")
            }
          >
            <input
              type="checkbox"
              className="peer sr-only"
              checked={search && searchAvailable}
              disabled={!searchAvailable || locked}
              onChange={(e) => setSearch(e.target.checked)}
            />
            <span
              aria-hidden="true"
              className="relative h-4 w-7 rounded-full bg-rule-strong transition-colors peer-checked:bg-accent peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent"
            >
              <span
                className={
                  "absolute top-0.5 left-0.5 size-3 rounded-full bg-paper transition-transform " +
                  (search && searchAvailable ? "translate-x-3" : "")
                }
              />
            </span>
            <span className="label text-ink-soft">Web search</span>
          </label>
        </div>

        {!searchAvailable && (
          <p className="mt-2 text-xs text-ink-faint">
            Web search is off: the backend reports no Tavily key, so the writer runs unaugmented.
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="submit"
          disabled={locked || busy}
          className="label rounded-md bg-ink px-6 py-3 text-paper transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? copy.busy : copy.cta}
        </button>
        <p className="text-xs text-ink-faint">{copy.hint}</p>
      </div>
    </form>
  );
}
