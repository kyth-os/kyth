import { useState } from "react";

import { confirmUserAction, runJustRecipe } from "../services/liveData";

/** Shared "run a mutating system action, then say what happened" helper.
 *
 * Factored out for the same reason LiveSectionCard was — Updates, Channels
 * and Guardian each need identical busy/status handling around a single
 * `invoke` that returns a human-readable string (or throws one). The
 * backend commands are the gate, not this: each validates its own input,
 * runs in the background, and keeps progress in the Hub. */
export function useSectionAction() {
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function run(id: string, pendingLabel: string, action: () => Promise<string>) {
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

  return { status, busy, run };
}

export function ActionButton({
  label,
  onClick,
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      className="action-button"
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
    <p className="card-copy action-status" style={{ fontSize: 12, marginTop: 12 }}>
      {status}
    </p>
  );
}

/** A `just <recipe>` button. The recipe runs as a captured background job;
 * password authentication, when needed, is a normal graphical askpass dialog
 * and progress/results stay in the Hub. */
export function RecipeButton({
  recipe,
  label,
  busy,
  run,
}: {
  recipe: string;
  label: string;
  busy: string | null;
  run: (id: string, pendingLabel: string, action: () => Promise<string>) => Promise<void>;
}) {
  return (
    <ActionButton
      label={busy === recipe ? `Starting ${recipe}…` : label}
      disabled={busy !== null}
      onClick={() =>
        confirmUserAction(`Run ${recipe}? It may change system state or open a privileged prompt.`) &&
        run(recipe, `Starting ${recipe}…`, () => runJustRecipe(recipe))
      }
    />
  );
}
