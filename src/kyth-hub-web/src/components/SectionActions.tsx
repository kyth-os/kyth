import { useState } from "react";

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
