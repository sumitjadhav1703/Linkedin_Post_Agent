import { useRef } from "react";

export type Mode = "hitl" | "auto";

const TABS: { id: Mode; name: string; verdict: string }[] = [
  { id: "hitl", name: "Human in the loop", verdict: "You cast the verdict" },
  { id: "auto", name: "Autonomous", verdict: "A second model casts the verdict" },
];

interface Props {
  mode: Mode;
  onChange: (mode: Mode) => void;
  locked: boolean;
}

/**
 * The toggle states the difference outright, because the difference is the
 * demo: identical writer, identical prompts, identical retry ceiling — one
 * swapped review node.
 */
export function ModeToggle({ mode, onChange, locked }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    const delta =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = (TABS.findIndex((t) => t.id === mode) + delta + TABS.length) % TABS.length;
    if (locked) return;
    onChange(TABS[next].id);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label="Which reviewer decides"
      onKeyDown={onKeyDown}
      className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-2"
    >
      {TABS.map((tab, i) => {
        const selected = tab.id === mode;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            disabled={locked && !selected}
            onClick={() => onChange(tab.id)}
            className={
              "group relative px-5 py-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-45 " +
              (selected ? "bg-surface" : "bg-paper hover:bg-surface/60")
            }
          >
            <span
              aria-hidden="true"
              className={
                "absolute inset-x-0 top-0 h-0.5 transition-colors " +
                (selected ? "bg-accent" : "bg-transparent")
              }
            />
            <span
              className={
                "block font-serif text-xl transition-colors " +
                (selected ? "text-ink" : "text-ink-soft")
              }
            >
              {tab.name}
            </span>
            <span
              className={
                "label mt-1.5 block " + (selected ? "text-accent" : "text-ink-faint")
              }
            >
              {tab.verdict}
            </span>
          </button>
        );
      })}
    </div>
  );
}
