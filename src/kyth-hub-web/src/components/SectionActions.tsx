import { useState } from "react";

import { runJustRecipe } from "../services/liveData";

/** Shared "run a mutating system action, then say what happened" helper.
 *
 * Factored out for the same reason LiveSectionCard was — Updates, Channels
 * and Guardian each need identical busy/status handling around a single
 * `invoke` that returns a human-readable string (or throws one). The
 * backend commands are the gate, not this: each validates its own input
 * and delegates to a `just` recipe that does its own privilege prompt. */
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
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "7px 16px",
        borderRadius: 999,
        border: "1px solid var(--hairline)",
        background: "var(--card)",
        fontWeight: 600,
        fontSize: 12.5,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {label}
    </button>
  );
}

export function ActionStatus({ status }: { status: string | null }) {
  if (!status) return null;
  return (
    <p className="card-copy" style={{ fontSize: 12, marginTop: 12 }}>
      {status}
    </p>
  );
}

/** A `just <recipe>` button. Recipes prompt for their own privilege and
 * run in their own terminal, so this only reports whether the spawn took —
 * same fire-and-forget contract kyth_shared::system::just::just_run has. */
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
        run(recipe, `Starting ${recipe}…`, async () => {
          const launched = await runJustRecipe(recipe);
          if (launched === null) return "Not available outside the Hub shell.";
          return launched ? `just ${recipe} is running in its own window.` : `Could not start just ${recipe}.`;
        })
      }
    />
  );
}

/** Read-only command text with a copy button — the honest rendering for
 * the kyth-shared helpers that return argv rather than running anything
 * (see liveData.ts's command-text section for why they aren't spawned). */
export function CommandLine({ label, command }: { label: string; command: string | null }) {
  const [copied, setCopied] = useState(false);
  if (!command) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
        {label}
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
        <code
          style={{
            flex: 1,
            fontSize: 12,
            padding: "8px 10px",
            borderRadius: 8,
            border: "1px solid var(--hairline)",
            overflowX: "auto",
            whiteSpace: "nowrap",
          }}
        >
          {command}
        </code>
        <ActionButton
          label={copied ? "Copied" : "Copy"}
          onClick={() => {
            navigator.clipboard?.writeText(command).then(
              () => setCopied(true),
              () => setCopied(false),
            );
          }}
        />
      </div>
    </div>
  );
}
