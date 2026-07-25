import { useEffect, useRef, useState } from "react";

export function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timeout.current) clearTimeout(timeout.current);
    },
    [],
  );

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      // Clipboard access is refused outside a secure context, and silently
      // doing nothing would look like a broken button.
      setState("failed");
    }
    if (timeout.current) clearTimeout(timeout.current);
    timeout.current = setTimeout(() => setState("idle"), 2000);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label="Copy post to clipboard"
        className="label rounded border border-rule-strong px-3 py-1.5 text-ink transition-colors hover:bg-ink hover:text-paper"
      >
        {state === "copied" ? "Copied" : state === "failed" ? "Copy blocked" : "Copy post"}
      </button>
      <span role="status" className="sr-only">
        {state === "copied"
          ? "Post copied to clipboard."
          : state === "failed"
            ? "Copy failed. The browser refused clipboard access."
            : ""}
      </span>
    </>
  );
}
