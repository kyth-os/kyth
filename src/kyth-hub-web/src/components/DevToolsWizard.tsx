import { useEffect, useMemo, useRef, useState } from "react";

import { isCancelledResult } from "../services/jobResults";
import {
  cancelDevToolsJob,
  fetchAiDevBoxStatus,
  fetchDevToolsCatalog,
  getInFlightJob,
  installSelectedDevTools,
  type AiDevBoxStatus,
  type DevTool,
} from "../services/liveData";
import { useSectionAction, ActionButton, ActionStatus, ProgressRing } from "./SectionActions";

type WizardStep = "welcome" | "select" | "review" | "install" | "done";

const CATEGORY_ORDER = ["editor", "agent-cli", "agent-desktop", "language", "utility", "local-ai"];

function groupByCategory(tools: DevTool[]): { key: string; label: string; tools: DevTool[] }[] {
  const groups = new Map<string, { key: string; label: string; tools: DevTool[] }>();
  for (const tool of tools) {
    const existing = groups.get(tool.category);
    if (existing) existing.tools.push(tool);
    else groups.set(tool.category, { key: tool.category, label: tool.category_label, tools: [tool] });
  }
  return CATEGORY_ORDER.map((key) => groups.get(key)).filter((group): group is NonNullable<typeof group> => group != null);
}

/** The "vibe coder" setup wizard: pick tools, review, install. Selection
 * state lives here only — the backend has no concept of a draft, so
 * closing mid-wizard loses the picks (same as any unsaved form) and a
 * fresh open reseeds from each tool's server-side default. */
export function DevToolsWizard({ onClose, catalog }: { onClose: () => void; catalog: DevTool[] }) {
  // Reopening during a tracked install lands on the install step with
  // its live status, not on a fresh welcome that pretends nothing runs.
  const [step, setStep] = useState<WizardStep>(() => (getInFlightJob("dev-tools") !== undefined ? "install" : "welcome"));
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(catalog.filter((tool) => tool.default_selected).map((tool) => tool.id)),
  );
  const { status, busy, run, runCancel } = useSectionAction("dev-tools");
  const startedHere = useRef(false);
  const [installOutcome, setInstallOutcome] = useState<"idle" | "running" | "ok" | "failed" | "cancelled">("idle");
  const [resumedFinished, setResumedFinished] = useState(false);

  useEffect(() => {
    if (installOutcome === "ok") setStep("done");
  }, [installOutcome]);

  // A resumed install has no local promise to await: poll the tracked
  // slot and move to done when it clears.
  useEffect(() => {
    if (step !== "install" || startedHere.current) return;
    const timer = window.setInterval(() => {
      if (getInFlightJob("dev-tools") === undefined) {
        window.clearInterval(timer);
        setResumedFinished(true);
        setStep("done");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [step]);
  const groups = useMemo(() => groupByCategory(catalog), [catalog]);
  const selectedTools = useMemo(() => catalog.filter((tool) => selected.has(tool.id)), [catalog, selected]);
  const installedIds = useMemo(() => new Set(catalog.filter((tool) => tool.installed).map((tool) => tool.id)), [catalog]);

  function toggle(id: string): void {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function startInstall(): void {
    startedHere.current = true;
    setInstallOutcome("running");
    setStep("install");
    void run("install-dev-tools", "Preparing the dev box…", async () => {
      try {
        const detail = await installSelectedDevTools([...selected]);
        setInstallOutcome(isCancelledResult(detail) ? "cancelled" : "ok");
        return detail;
      } catch (error) {
        setInstallOutcome("failed");
        throw error;
      }
    });
  }

  return (
    <div className="dev-tools-wizard-overlay" role="dialog" aria-modal="true" aria-label="Dev Tools setup wizard">
      <div className="dev-tools-wizard glass">
        <div className="dev-tools-wizard-header">
          <span className="app-eyebrow">Vibe coder setup</span>
          <h2>Set up your dev box</h2>
          <button className="dev-tools-wizard-close" onClick={onClose} aria-label="Close wizard">×</button>
        </div>

        {step === "welcome" && (
          <div className="dev-tools-wizard-body">
            <p>
              This creates (or reuses) your isolated <code>kyth-ai-dev</code> box and installs exactly
              the editors, AI coding agents, and tools you pick — nothing else.
            </p>
            <ul className="dev-tools-wizard-bullets">
              <li>Pick from real IDEs and agent CLIs/desktop apps below</li>
              <li>Everything installs in one tracked, cancellable step</li>
              <li>Re-run anytime to add more tools — already-installed ones are skipped</li>
            </ul>
            <div className="dev-tools-wizard-actions">
              <ActionButton label="Get started" primary onClick={() => setStep("select")} />
            </div>
          </div>
        )}

        {step === "select" && (
          <div className="dev-tools-wizard-body">
            {groups.map((group) => (
              <section key={group.key} className="dev-tools-wizard-group">
                <h3>{group.label}</h3>
                <div className="dev-tools-wizard-grid">
                  {group.tools.map((tool) => (
                    <label
                      key={tool.id}
                      className={`dev-tools-wizard-card ${selected.has(tool.id) ? "dev-tools-wizard-card-selected" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(tool.id)}
                        onChange={() => toggle(tool.id)}
                      />
                      <div className="dev-tools-wizard-card-body">
                        <div className="dev-tools-wizard-card-title">
                          <strong>{tool.name}</strong>
                          {tool.unofficial && <span className="dev-tools-badge-unofficial">Unofficial</span>}
                          {installedIds.has(tool.id) && <span className="dev-tools-badge-installed">Installed</span>}
                        </div>
                        <p>{tool.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </section>
            ))}
            <div className="dev-tools-wizard-actions">
              <ActionButton label="Back" onClick={() => setStep("welcome")} />
              <ActionButton
                label={`Review (${selected.size} selected)`}
                primary
                disabled={selected.size === 0}
                onClick={() => setStep("review")}
              />
            </div>
          </div>
        )}

        {step === "review" && (
          <div className="dev-tools-wizard-body">
            <p>Installing {selectedTools.length} tool(s):</p>
            <ul className="dev-tools-wizard-review-list">
              {selectedTools.map((tool) => (
                <li key={tool.id}>
                  {tool.name}
                  {tool.unofficial && <span className="dev-tools-badge-unofficial"> Unofficial</span>}
                </li>
              ))}
            </ul>
            {selectedTools.some((tool) => tool.unofficial) && (
              <p className="dev-tools-wizard-warning">
                One or more selected tools are unofficial community packages, not published by their
                original vendor. Review the details on their project page before relying on them.
              </p>
            )}
            <div className="dev-tools-wizard-actions">
              <ActionButton label="Back" onClick={() => setStep("select")} />
              <ActionButton label="Install" primary onClick={startInstall} />
            </div>
          </div>
        )}

        {step === "install" && (
          <div className="dev-tools-wizard-body">
            <div className="app-loading-state hub-progress-inline"><ProgressRing size={30} /> {status ?? "Working…"}</div>
            <div className="dev-tools-wizard-actions">
              {(busy !== null || (!startedHere.current && getInFlightJob("dev-tools") !== undefined)) && (
                <ActionButton label="Cancel setup" onClick={() => void runCancel("cancel-dev-tools", "Cancelling…", cancelDevToolsJob)} />
              )}
              {startedHere.current && installOutcome !== "running" && installOutcome !== "ok" && (
                <>
                  <ActionButton label="Back to review" onClick={() => setStep("review")} />
                  <ActionButton label="Retry install" primary onClick={startInstall} />
                </>
              )}
              <ActionButton label="Close" onClick={onClose} />
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="dev-tools-wizard-body">
            {resumedFinished && <p>The setup that was already running has finished. Close to see the updated tool list.</p>}
            <ActionStatus status={status} />
            <div className="dev-tools-wizard-actions">
              <ActionButton label="Close" primary onClick={onClose} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function DevToolsOverview() {
  const [catalog, setCatalog] = useState<DevTool[] | null>(null);
  const [boxStatus, setBoxStatus] = useState<AiDevBoxStatus | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const resumedInstall = getInFlightJob("dev-tools") !== undefined;

  async function refresh(): Promise<void> {
    const [nextCatalog, nextStatus] = await Promise.all([fetchDevToolsCatalog(), fetchAiDevBoxStatus()]);
    setCatalog(nextCatalog);
    setBoxStatus(nextStatus);
    setLoadFailed(nextCatalog === null || nextStatus === null);
    setLoaded(true);
  }

  useEffect(() => { void refresh(); }, []);

  const installedCount = catalog?.filter((tool) => tool.installed).length ?? 0;

  return (
    <div className="dev-tools-page">
      <div className="app-store-hero">
        <div>
          <span className="app-eyebrow">KythOS Dev Tools</span>
          <h2>Your AI-native dev box</h2>
          <p>
            Set up an isolated development environment with the editors and AI coding agents you
            want — VS Code, Claude Code, Codex, and more — in one guided setup.
          </p>
        </div>
        <div className="app-store-hero-art"><span>✦</span><i /><i /><i /></div>
      </div>

      {!loaded && <div className="app-loading-state hub-progress-inline"><ProgressRing size={24} /> Loading Dev Tools status…</div>}

      {loaded && loadFailed && (
        <section className="app-catalog-section">
          <p className="app-subsection-copy">Couldn&apos;t check the dev box or the tool catalog — a status read failed, so nothing here can be shown yet. Installed tools and an existing box are unaffected.</p>
          <div className="dev-tools-wizard-actions">
            <ActionButton label="Retry" primary onClick={() => void refresh()} />
          </div>
        </section>
      )}

      {loaded && !loadFailed && (
        <>
          <div className="app-stat-row">
            <div><span>Dev box</span><strong>{boxStatus?.exists ? "Ready" : "Not created yet"}</strong></div>
            <div><span>GPU acceleration</span><strong>{boxStatus?.gpu ?? "—"}</strong></div>
            <div><span>Tools installed</span><strong>{installedCount} / {catalog?.length ?? 0}</strong></div>
          </div>

          {resumedInstall && (
            <p className="card-copy action-status">A previous setup is still running; its progress resumes if you reopen the wizard.</p>
          )}

          <section className="app-catalog-section">
            <div className="app-section-heading">
              <div>
                <span className="app-eyebrow">Get started</span>
                <h2>Install dev tools</h2>
              </div>
            </div>
            <p className="app-subsection-copy">
              Choose editors, AI agent CLIs and desktop apps, languages, and utilities. Everything
              installs into the isolated <code>{boxStatus?.box_name ?? "kyth-ai-dev"}</code> box (host
              agent apps install directly), so your base system stays untouched.
            </p>
            <div className="dev-tools-wizard-actions">
              <ActionButton label={boxStatus?.exists ? "Add more tools" : "Create dev box & install tools"} primary onClick={() => setWizardOpen(true)} />
            </div>
          </section>

          {catalog && catalog.length > 0 && (
            <section className="app-secondary-section">
              <div className="app-section-heading">
                <div>
                  <span className="app-eyebrow">Status</span>
                  <h2>Installed tools</h2>
                </div>
              </div>
              <div className="dev-tools-status-grid">
                {catalog.map((tool) => (
                  <div key={tool.id} className={`dev-tools-status-item ${tool.installed ? "dev-tools-status-item-ok" : ""}`}>
                    <span>{tool.name}</span>
                    <strong>{tool.installed ? "Installed" : "Not installed"}</strong>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {wizardOpen && catalog && (
        <DevToolsWizard
          catalog={catalog}
          onClose={() => { setWizardOpen(false); void refresh(); }}
        />
      )}
    </div>
  );
}
