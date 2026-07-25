import { useCallback, useEffect, useState } from "react";
import { getHealth, toApiError, type ApiError, type Health } from "../lib/api";

interface HealthState {
  data: Health | null;
  error: ApiError | null;
  loading: boolean;
}

/**
 * Fetched once on load. Everything configurable — attempt ceiling, model names,
 * whether search is even possible — comes from here rather than from constants
 * in this codebase, so the UI cannot drift from the server it is talking to.
 */
export function useHealth() {
  const [state, setState] = useState<HealthState>({
    data: null,
    error: null,
    loading: true,
  });

  const refetch = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      const data = await getHealth();
      setState({ data, error: null, loading: false });
    } catch (err) {
      setState({ data: null, error: toApiError(err), loading: false });
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getHealth();
        if (!cancelled) setState({ data, error: null, loading: false });
      } catch (err) {
        if (!cancelled) setState({ data: null, error: toApiError(err), loading: false });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { ...state, refetch };
}
