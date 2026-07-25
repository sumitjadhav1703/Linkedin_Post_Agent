import { useEffect, useState } from "react";

/**
 * Seconds since `startedAt`, ticking while `running`.
 *
 * Only the autonomous mode uses this. Its wait is bounded and machine-paced, so
 * showing the clock is honest information. The human mode's wait is unbounded by
 * design and a running timer there would only imply a deadline that isn't real.
 */
export function useElapsed(startedAt: number | null, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running || startedAt === null) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running, startedAt]);

  if (startedAt === null) return 0;
  return Math.max(0, Math.floor((now - startedAt) / 1000));
}
