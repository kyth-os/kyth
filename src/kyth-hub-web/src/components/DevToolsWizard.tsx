import { useEffect, useMemo, useState } from "react";

import {
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
  const [step, setStep] = useState<WizardStep>("welcome");
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(catalog.filter((tool) => tool.default_selected).map((tool) => tool.id)),
  );
  const { status, run } = useSectionAction("dev-tools");
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
    setStep("install");
    void run("install-dev-tools", "Preparing the dev box…", () => installSelectedDevTools([...selected])).then(() => {
      setStep("done");
    });
  }

  return (
    <div className="dev-tools-wizard-overlay" role="dialog" aria-modal="true" aria-label="Dev Tools setup wizard">
      <div className="dev-tools-wizard glass">
        <div className="dev-tools-wizard-header">
          <span className="app-eyebrow">Vibe coder setup</span>
          <h2>Set up your dev box</h2>
          {step !== "install" && (
            <button className="dev-tools-wizard-close" onClick={onClose} aria-label="Close wizard">×</button>
          )}
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
          </div>
        )}

        {step === "done" && (
          <div className="dev-tools-wizard-body">
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
  const [wizardOpen, setWizardOpen] = useState(false);
  const resumedInstall = getInFlightJob("dev-tools") !== undefined;

  async function refresh(): Promise<void> {
    const [nextCatalog, nextStatus] = await Promise.all([fetchDevToolsCatalog(), fetchAiDevBoxStatus()]);
    setCatalog(nextCatalog);
    setBoxStatus(nextStatus);
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

      {!loaded && <div className="app-loading-state"><span className="app-spinner" /> Loading Dev Tools status…</div>}

      {loaded && (
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
