import { useState } from "react";

import {
  cancelDevToolsJob,
  cancelGamingJob,
  cancelGuardianCheck,
  cancelHubAction,
  cancelInstall,
  cancelJob,
  cancelPrivilegedAction,
  cancelSecurityJob,
  cancelUpdateJob,
  cancelVpnConnection,
  confirmUserAction,
  getInFlightJob,
  runHubRecipeAction,
} from "../services/liveData";
import type { JobDomain } from "../services/liveData";

/** Shared "run a mutating system action, then say what happened" helper.
 *
 * Factored out for the same reason LiveSectionCard was — Updates, Channels
 * and Guardian each need identical busy/status handling around a single
 * `invoke` that returns a human-readable string (or throws one). The
 * backend commands are the gate, not this: each validates its own input,
 * runs in the background, and keeps progress in the Hub. */
export function useSectionAction(trackedDomain?: JobDomain) {
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // Component state is lost on reload, but a tracked backend job keeps
  // running (reattached from persisted in-flight ids) — surface that
  // instead of a blank slate. Read live every render, not once at mount:
  // a job that settled elsewhere must clear the notice, and one started
  // elsewhere after mount must raise it (otherwise the next launch
  // errors "already running" with no explanation).
  const [resumedDismissed, setResumedDismissed] = useState(false);
  const resumedNote =
    !resumedDismissed &&
    busy === null &&
    status === null &&
    trackedDomain !== undefined &&
    getInFlightJob(trackedDomain) !== undefined
      ? "A previous action is still running; its progress resumes here."
      : null;

  async function run(id: string, pendingLabel: string, action: () => Promise<string>) {
    setResumedDismissed(true);
    setBusy(id);
    setStatus(pendingLabel);
    try {
      setStatus(await action());
    } catch (err) {
      // Tauri rejects a Result::Err with the bare string, not an Error.
      setStatus(`Failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(null);
    }
  }

  return { status: resumedNote ?? status, busy, run };
}

export function ActionButton({
  label,
  onClick,
  disabled = false,
  primary = false,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      className={`action-button${primary ? " action-button-primary" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}

export function ActionStatus({ status }: { status: string | null }) {
  if (!status) return null;
  return (
    <p className="card-copy action-status" role="status" key={status} style={{ fontSize: 12, marginTop: 12 }}>
      {status}
    </p>
  );
}

/** Shared progress ring for any tracked job that reports a 0-100 percent
 * (or none, for an indeterminate spin) — the same visual language Updates
 * uses for staging, generalized so installs/migrations/dev-tools setup
 * don't each reinvent the SVG math. `pct === undefined` renders spinning
 * and indeterminate; a number renders a determinate sweep with a label. */
export function ProgressRing({ pct, size = 40 }: { pct?: number; size?: number }) {
  const indeterminate = pct === undefined;
  return (
    <div
      className={`hub-progress-ring${indeterminate ? " hub-progress-ring-indeterminate" : ""}`}
      style={{ width: size, height: size, flexBasis: size }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 48 48" focusable="false">
        <circle className="hub-progress-ring-track" cx="24" cy="24" r="19" pathLength="100" />
        <circle
          className="hub-progress-ring-value"
          cx="24"
          cy="24"
          r="19"
          pathLength="100"
          style={indeterminate ? undefined : { strokeDashoffset: 100 - pct }}
        />
      </svg>
      {!indeterminate && <span>{pct}%</span>}
    </div>
  );
}

/** Cancel entry point for each tracked job domain. RecipeButton's Cancel
 * must stop the domain its recipe actually runs in — every recipe runs as
 * a `hub-action` job, while installs/Kali/gaming jobs use their own
 * domains, so a single hard-coded cancel target silently cancels nothing
 * outside `hub-action`. */
export const CANCEL_FOR_DOMAIN: Record<JobDomain, () => Promise<string>> = {
  guardian: cancelGuardianCheck,
  privileged: cancelPrivilegedAction,
  "hub-action": cancelHubAction,
  update: cancelUpdateJob,
  job: cancelJob,
  install: cancelInstall,
  security: cancelSecurityJob,
  gaming: cancelGamingJob,
  vpn: cancelVpnConnection,
  "dev-tools": cancelDevToolsJob,
};

export function cancelForDomain(domain: JobDomain): () => Promise<string> {
  return CANCEL_FOR_DOMAIN[domain];
}

/** A `just <recipe>` button. The recipe runs as a captured background job;
 * password authentication, when needed, is a normal graphical askpass dialog
 * and progress/results stay in the Hub. */
export function RecipeButton({
  recipe,
  label,
  busy,
  run,
  domain = "hub-action",
}: {
  recipe: string;
  label: string;
  busy: string | null;
  run: (id: string, pendingLabel: string, action: () => Promise<string>) => Promise<void>;
  domain?: JobDomain;
}) {
  if (busy === recipe) {
    return (
      <span className="hub-progress-inline">
        <ProgressRing size={22} />
        <ActionButton
          label="Cancel"
          onClick={() => run(`cancel-${recipe}`, "Cancelling…", CANCEL_FOR_DOMAIN[domain])}
        />
      </span>
    );
  }
  return (
    <ActionButton
      label={label}
      disabled={busy !== null}
      onClick={() =>
        confirmUserAction(`Run ${recipe}? It may change system state or open a privileged prompt.`) &&
        run(recipe, `Starting ${recipe}…`, () => runHubRecipeAction(recipe))
      }
    />
  );
}
