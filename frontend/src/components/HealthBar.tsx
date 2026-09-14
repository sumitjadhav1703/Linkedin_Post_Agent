import type { ApiError, Health } from "../lib/api";
import { API_BASE } from "../lib/api";

interface Props {
  health: Health | null;
  error: ApiError | null;
  loading: boolean;
  /** A later request failed to connect, so the load-time health check is stale. */
  degraded: boolean;
}

/** Masthead. Everything in it is read off /api/health, nothing is hardcoded. */
export function HealthBar({
  health,
  error,
  loading,
  degraded,
}: Props) {
  const tone = loading
    ? {
        dot: "bg-ink-faint",
        text: "text-ink-faint",
        label: "Contacting backend",
      }
    : error || !health
      ? {
          dot: "bg-bad",
          text: "text-bad",
          label: "Backend unreachable",
        }
      : degraded
        ? {
            dot: "bg-bad",
            text: "text-bad",
            label: "Backend stopped answering",
          }
        : !health.groq_key
          ? {
              dot: "bg-bad",
              text: "text-bad",
              label: "No Groq key",
            }
          : {
              dot: "bg-ok",
              text: "text-ok",
              label: "Backend ready",
            };

  return (
    <header className="border-b border-rule">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-5 py-3 sm:px-8">
        <div className="flex items-center gap-4">
          <span className="font-mono text-xs font-bold tracking-[0.3em] uppercase">
            Copy&thinsp;/&thinsp;Desk
          </span>

          <span className={`flex items-center gap-2 ${tone.text}`}>
            <span
              className={`size-1.5 rounded-full ${tone.dot}`}
              aria-hidden="true"
            />
            <span className="label">{tone.label}</span>
          </span>
        </div>

        <dl className="flex flex-wrap items-center gap-x-6 gap-y-1">
          <Meta label="Writer" value={health?.writer_model} />
          <Meta label="Reviewer" value={health?.reviewer_model} />

          <Meta
            label="Attempt cap"
            value={health ? String(health.max_attempts) : undefined}
          />

          <Meta
            label="Search"
            value={
              health
                ? health.tavily_key
                  ? "available"
                  : "off"
                : undefined
            }
          />

          <Meta
            label="API"
            value={API_BASE.replace(/^https?:\/\//, "")}
          />
        </dl>
      </div>
    </header>
  );
}

function Meta({
  label,
  value,
}: {
  label: string;
  value?: string;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="label text-ink-faint">{label}</dt>
      <dd className="font-mono text-[11px] text-ink-soft">
        {value ?? "—"}
      </dd>
    </div>
  );
}
