import { useState } from "react";
import { AutoLedger } from "./components/AutoLedger";
import { ErrorBanner } from "./components/ErrorBanner";
import { HealthBar } from "./components/HealthBar";
import { ModeToggle, type Mode } from "./components/ModeToggle";
import { TopicForm } from "./components/TopicForm";
import { HitlDesk } from "./components/HitlDesk";
import { useAutoSession } from "./hooks/useAutoSession";
import { useHealth } from "./hooks/useHealth";
import { useHitlSession } from "./hooks/useHitlSession";

export function App() {
  const [mode, setMode] = useState<Mode>("hitl");
  const health = useHealth();
  const hitl = useHitlSession();
  const auto = useAutoSession();

  // "Locked" means a run owns the page: the mode can't be swapped and a second
  // run can't be started underneath the first.
  const hitlBusy = hitl.state.phase === "drafting" || hitl.state.phase === "revising";
  const hitlLocked = hitlBusy || hitl.state.phase === "awaiting_review";
  const autoBusy = auto.state.phase === "starting";
  const autoLocked = autoBusy || auto.state.phase === "running";
  const locked = mode === "hitl" ? hitlLocked : autoLocked;

  // The health check runs once at load, so a backend that dies afterwards would
  // otherwise leave a green light in the masthead over a failing page.
  const offline = Boolean(hitl.state.error?.isOffline || auto.state.error?.isOffline);

  const maxAttempts = health.data?.max_attempts ?? 3;
  const sessionId =
    mode === "hitl" ? hitl.state.threadId : auto.state.jobId;

  return (
    <div className="dot-grid min-h-dvh">
      <HealthBar
        health={health.data}
        error={health.error}
        loading={health.loading}
        degraded={offline}
      />

      <main className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <section className="max-w-2xl">
          <h1 className="font-serif text-4xl leading-[1.1] text-ink sm:text-5xl">
            One writer.
            <br />
            Two ways to be judged.
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-ink-soft">
            The same LangGraph writer drafts a LinkedIn post either way — same model,
            same prompts, same three-attempt ceiling. The only node that changes is the
            one that says yes or no.
          </p>
        </section>

        {health.error && (
          <div className="mt-10 max-w-2xl">
            <ErrorBanner error={health.error} onRetry={() => void health.refetch()} />
          </div>
        )}

        {health.data && !health.data.mistral_key && <SetupNotice />}

        {health.data && health.data.mistral_key && (
          <div className="mt-12">
            <ModeToggle mode={mode} onChange={setMode} locked={locked} />

            <section
              id="panel-hitl"
              role="tabpanel"
              aria-labelledby="tab-hitl"
              hidden={mode !== "hitl"}
              tabIndex={0}
              className="mt-10 space-y-12"
            >
              <div className="max-w-2xl">
                <TopicForm
                  mode="hitl"
                  onSubmit={(topic, search) => {
                    hitl.reset();
                    void hitl.start(topic, search);
                  }}
                  busy={hitlBusy}
                  locked={hitlLocked}
                  searchAvailable={health.data.tavily_key}
                />
              </div>

              {hitl.state.phase === "idle" ? (
                <Explainer
                  steps={[
                    "The writer drafts.",
                    "The graph suspends on interrupt() and waits — indefinitely.",
                    "You approve, or send a note and it rewrites.",
                  ]}
                  note="Nothing runs while it waits on you. That pause is the whole point of the mode."
                />
              ) : (
                <HitlDesk
                  state={hitl.state}
                  maxAttempts={maxAttempts}
                  onApprove={hitl.approve}
                  onFeedback={hitl.submit}
                  onRetry={hitl.retryLast}
                  onReset={hitl.reset}
                />
              )}
            </section>

            <section
              id="panel-auto"
              role="tabpanel"
              aria-labelledby="tab-auto"
              hidden={mode !== "auto"}
              tabIndex={0}
              className="mt-10 space-y-12"
            >
              <div className="max-w-2xl">
                <TopicForm
                  mode="auto"
                  onSubmit={(topic, search) => {
                    auto.reset();
                    void auto.start(topic, search);
                  }}
                  busy={autoBusy}
                  locked={autoLocked}
                  searchAvailable={health.data.tavily_key}
                />
              </div>

              {auto.state.phase === "idle" ? (
                <Explainer
                  steps={[
                    "The writer drafts.",
                    "A second model rules on it and writes a critique if it fails.",
                    "The writer rewrites against that critique, up to the attempt cap.",
                  ]}
                  note="No one is asked anything. The job runs to a verdict on the server whether or not this tab is open."
                />
              ) : (
                <AutoLedger
                  state={auto.state}
                  maxAttempts={maxAttempts}
                  onResumePolling={auto.resumePolling}
                  onReset={auto.reset}
                />
              )}
            </section>
          </div>
        )}
      </main>

      <footer className="mt-20 border-t border-rule">
        <div className="mx-auto flex max-w-5xl flex-wrap items-baseline justify-between gap-x-8 gap-y-3 px-5 py-8 sm:px-8">
          <p className="max-w-md text-xs leading-relaxed text-ink-faint">
            Both modes import the same writer chain. The human graph needs a
            checkpointer because it has to put itself down and pick itself back up;
            the autonomous one never pauses, so it needs none.
          </p>
          <p className="label text-ink-faint">
            Session{" "}
            <span className="font-mono text-[11px] normal-case tracking-normal text-ink-soft">
              {sessionId ? sessionId.slice(0, 12) : "—"}
            </span>
          </p>
        </div>
      </footer>
    </div>
  );
}

function Explainer({ steps, note }: { steps: string[]; note: string }) {
  return (
    <div className="max-w-2xl border-t border-rule pt-8">
      <ol className="space-y-3">
        {steps.map((step, i) => (
          <li key={step} className="flex gap-4">
            <span className="label pt-1 text-accent">{String(i + 1).padStart(2, "0")}</span>
            <span className="font-serif text-xl leading-snug text-ink-soft">{step}</span>
          </li>
        ))}
      </ol>
      <p className="mt-6 max-w-prose text-xs leading-relaxed text-ink-faint">{note}</p>
    </div>
  );
}

/**
 * Without a key on the server there is nothing to demo, so the form is replaced
 * rather than left in place to fail on submit.
 */
function SetupNotice() {
  return (
    <section className="mt-10 max-w-2xl rounded-lg border border-warn/40 bg-warn-wash p-6">
      <h2 className="label text-warn">Backend has no Mistral key</h2>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft">
        The API is up and answering, but <code className="font-mono text-xs">/api/health</code>{" "}
        reports <code className="font-mono text-xs">mistral_key: false</code>, so neither mode
        can write anything. Put <code className="font-mono text-xs">MISTRAL_API_KEY</code> in the
        backend's <code className="font-mono text-xs">.env</code> and restart it.
      </p>
      <p className="mt-3 text-xs leading-relaxed text-ink-faint">
        Health reports presence only — no key value ever reaches this page.
      </p>
    </section>
  );
}
