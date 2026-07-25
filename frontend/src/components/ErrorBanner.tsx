import type { ApiError } from "../lib/api";
import { API_BASE } from "../lib/api";

interface Props {
  error: ApiError;
  onRetry?: () => void;
  retryLabel?: string;
  onReset?: () => void;
  resetLabel?: string;
}

/**
 * The four failure modes read differently to a user, so they are worded
 * differently. A 404 is not a bug they can retry their way out of, and an
 * unreachable backend is not the same as a backend that answered with a refusal.
 */
function explain(error: ApiError): { heading: string; body: string } {
  if (error.isOffline) {
    return {
      heading: "Backend not answering",
      body: `Nothing responded at ${API_BASE}. Start the API with \`uvicorn app.api:app --port 8000\`, then retry — the run above is lost either way.`,
    };
  }
  if (error.isExpiredSession) {
    return {
      heading: "Session expired",
      body: "The server no longer holds this session. Sessions live in process memory, so restarting the backend clears every one of them. The draft above is still readable, but it can't be continued — start over to open a new one.",
    };
  }
  if (error.status === 502) {
    return {
      heading: "The model call failed",
      body: error.detail,
    };
  }
  return { heading: `Request failed (${error.status})`, body: error.detail };
}

export function ErrorBanner({ error, onRetry, retryLabel = "Retry", onReset, resetLabel = "Start over" }: Props) {
  const { heading, body } = explain(error);

  return (
    <div
      role="alert"
      className="rounded-md border border-bad/40 bg-bad-wash p-4 sm:p-5"
    >
      <p className="label text-bad">{heading}</p>
      <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-soft break-words">
        {body}
      </p>
      {(onRetry || onReset) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="label rounded border border-bad/50 bg-bad/10 px-3 py-1.5 text-bad transition-colors hover:bg-bad/20"
            >
              {retryLabel}
            </button>
          )}
          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="label rounded border border-rule px-3 py-1.5 text-ink-soft transition-colors hover:border-rule-strong hover:text-ink"
            >
              {resetLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
