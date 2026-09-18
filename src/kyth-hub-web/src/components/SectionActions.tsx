import { useState } from "react";

import {
  cancelGamingJob,
  cancelGuardianCheck,
  cancelHubAction,
  cancelInstall,
  cancelJob,
  cancelPrivilegedAction,
  cancelSecurityJob,
  cancelUpdateJob,
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
  // instead of a blank slate.
  const [resumedNote, setResumedNote] = useState<string | null>(() =>
    trackedDomain !== undefined && getInFlightJob(trackedDomain) !== undefined
      ? "A previous action is still running; its progress resumes here."
      : null,
  );

  async function run(id: string, pendingLabel: string, action: () => Promise<string>) {
    setResumedNote(null);
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
    <p className="card-copy action-status" role="status" style={{ fontSize: 12, marginTop: 12 }}>
      {status}
    </p>
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
      <ActionButton
        label="Cancel"
        onClick={() => run(`cancel-${recipe}`, "Cancelling…", CANCEL_FOR_DOMAIN[domain])}
      />
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
