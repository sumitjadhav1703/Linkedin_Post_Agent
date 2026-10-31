// The only module that talks to the backend. Nothing else imports fetch.
//
// Every id (`thread_id`, `job_id`) originates on the server; this client stores
// what it was handed and echoes it back. It never mints one.

export const API_BASE =
  (import.meta.env?.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export interface Health {
  status: string;
  provider: "nvidia";
  nvidia_key: boolean;
  tavily_key: boolean;
  writer_model: string;
  reviewer_model: string;
  max_attempts: number;
}

export type StopReason = "approved" | "max_attempts";

export type HitlStatus = "awaiting_review" | "completed";

/** Response shape of both /api/hitl/start and /api/hitl/resume. */
export interface HitlResponse {
  thread_id: string;
  status: HitlStatus;
  draft: string;
  attempt: number;
  /** Present while awaiting_review. */
  instruction?: string;
  /** Present once completed. */
  is_approved?: boolean;
  stop_reason?: StopReason;
}

/** One row of the autonomous run. `approved` is null while the reviewer is still ruling. */
export interface AutoHistoryEntry {
  attempt: number;
  draft: string;
  approved: boolean | null;
  feedback: string | null;
}

export type AutoStatus = "running" | "completed" | "error";

export interface AutoStartResponse {
  job_id: string;
  status: AutoStatus;
}

export interface AutoStatusResponse {
  job_id: string;
  status: AutoStatus;
  attempt: number;
  history: AutoHistoryEntry[];
  draft: string | null;
  is_approved: boolean | null;
  stop_reason: StopReason | null;
  error: string | null;
  error_status?: number | null;
}

/**
 * Every failure reaches the UI as one of these.
 *
 * `status: 0` means the request never got an HTTP response at all — the backend
 * is down, or the browser dropped the connection. That case is distinct from a
 * 404 (server alive, session gone) and the UI words them differently.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** No HTTP response — backend unreachable rather than refusing. */
  get isOffline(): boolean {
    return this.status === 0;
  }

  /** In-memory session state is gone; the run cannot be continued. */
  get isExpiredSession(): boolean {
    return this.status === 404 || this.status === 410;
  }
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError(0, err instanceof Error ? err.message : "Unexpected error");
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  let res: Response;
  let text: string;
  try {
    res = await fetch(`${API_BASE.replace(/\/+$/, "")}${path}`, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
      headers: { "content-type": "application/json", ...init?.headers },
    });
    text = await res.text();
  } catch {
    throw new ApiError(0, `Could not complete the request to ${API_BASE}. The server may still be running the job; check its progress before starting another run.`);
  }

  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // Proxies may return HTML instead of the expected JSON contract.
  }
  if (!res.ok) {
    const detail = body && typeof body === "object" && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : res.statusText || `Request failed with ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  if (!body || typeof body !== "object") {
    throw new ApiError(502, "The backend returned an invalid response. Check service availability before retrying.");
  }
  return body as T;
}

export const getHealth = () => request<Health>("/api/health");

export const hitlStart = (topic: string, enableSearch: boolean) =>
  request<HitlResponse>("/api/hitl/start", {
    method: "POST",
    body: JSON.stringify({ topic, enable_search: enableSearch }),
  }, 180000);

export const hitlResume = (threadId: string, feedback: string) =>
  request<HitlResponse>("/api/hitl/resume", {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId, feedback }),
  }, 180000);

export const autoStart = (topic: string, enableSearch: boolean) =>
  request<AutoStartResponse>("/api/auto/start", {
    method: "POST",
    body: JSON.stringify({ topic, enable_search: enableSearch }),
  });

export const autoStatus = (jobId: string) =>
  request<AutoStatusResponse>(`/api/auto/status/${jobId}`);

/**
 * Words the backend reads as approval. Anything else it treats as a critique.
 *
 * The UI sends "approved" from a dedicated button, so the user never has to
 * guess. This list exists to catch the opposite mistake: typing "ok, but drop
 * the hashtags" into the feedback box, where the leading word would silently
 * ship the draft instead of revising it.
 */
const APPROVAL_WORDS = new Set([
  "approved",
  "approve",
  "yes",
  "ok",
  "okay",
  "good",
  "lgtm",
  "ship it",
]);

export const readsAsApproval = (text: string) =>
  APPROVAL_WORDS.has(text.trim().toLowerCase());

export const APPROVAL_TOKEN = "approved";
