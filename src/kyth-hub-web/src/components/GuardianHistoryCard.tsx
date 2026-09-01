import { useMemo, useState } from "react";
import type { GuardianEvent } from "../data/dashboardTypes";
import type { GuardianPendingItem } from "../services/liveData";
import { ActionButton } from "./SectionActions";

const dot: Record<string, string> = {
  ok: "var(--status-ok)",
  warn: "var(--status-warn)",
  error: "var(--status-error)",
};

// `events` is required and never defaults to a fixture: a failed or
// not-yet-resolved Guardian read must render the empty state below, not
// four fabricated events presented as this machine's health history.
// `live` toggles the badge; the events come from guardian_snapshot.
export function GuardianHistoryCard({
  events,
  pending = [],
  live = false,
  onConfirm,
  onDismiss,
}: {
  events: GuardianEvent[];
  pending?: GuardianPendingItem[];
  live?: boolean;
  onConfirm?: (recipeId: string) => Promise<string>;
  onDismiss?: (recipeId: string) => Promise<string>;
}) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busyRecipe, setBusyRecipe] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [dismissedRecipes, setDismissedRecipes] = useState<Set<string>>(new Set());
  const pendingByRecipe = useMemo(() => new Map(pending.map((item) => [item.recipeId, item])), [pending]);

  async function runAction(recipeId: string, action: (id: string) => Promise<string>, hideAfter = false) {
    setBusyRecipe(recipeId);
    setActionStatus(null);
    try {
      setActionStatus(await action(recipeId));
      if (hideAfter) setDismissedRecipes((current) => new Set(current).add(recipeId));
    } catch (error) {
      setActionStatus(`Failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusyRecipe(null);
    }
  }

  const visibleEvents = events.filter((event) => !event.recipeId || !dismissedRecipes.has(event.recipeId));

  return (
    <div className="glass dashboard-card activity-card" style={{ padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <p className="card-title">Guardian activity</p>
          {live && <span className="pill pill-ok">Live</span>}
        </div>
        <span className="card-copy" style={{ fontSize: 11.5 }}>
          {live ? "Most recent" : "Recent"}
        </span>
      </div>
      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 2 }}>
        {visibleEvents.length === 0 && (
          <p className="card-copy" style={{ padding: "10px 4px" }}>
            No Guardian activity recorded yet.
          </p>
        )}
        {visibleEvents.map((event, i) => {
          const recommendation = event.recipeId ? pendingByRecipe.get(event.recipeId) : undefined;
          const actionable = Boolean(recommendation && onConfirm && onDismiss && event.action === "recommended");
          const isExpanded = expanded === i;
          return <div
            key={`${event.title}-${i}`}
            className="guardian-history-item"
          >
            <button
              type="button"
              className="guardian-history-row"
              aria-expanded={isExpanded}
              onClick={() => setExpanded(isExpanded ? null : i)}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: dot[event.status],
                  boxShadow: `0 0 0 4px color-mix(in srgb, ${dot[event.status]} 18%, transparent)`,
                  flexShrink: 0,
                }}
              />
              <span style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
                <span style={{ display: "block", fontSize: 13, fontWeight: 600 }}>{event.title}</span>
                {!isExpanded && <span className="card-copy" style={{ display: "block", fontSize: 11.5 }}>{event.detail}</span>}
              </span>
              <span className="card-copy" style={{ fontSize: 11, flexShrink: 0 }}>{event.when}</span>
              <span className="guardian-history-chevron" aria-hidden="true">{isExpanded ? "⌃" : "⌄"}</span>
            </button>
            {isExpanded && (
              <div className="guardian-history-expanded">
                <p className="card-copy" style={{ margin: 0, fontSize: 11.5 }}>{event.detail}</p>
                {actionable && recommendation && (
                  <div className="guardian-history-actions">
                    <ActionButton
                      label={busyRecipe === recommendation.recipeId ? "Running…" : "Confirm & run"}
                      disabled={busyRecipe !== null}
                      onClick={() => void runAction(recommendation.recipeId, onConfirm!)}
                    />
                    <ActionButton
                      label={busyRecipe === recommendation.recipeId ? "Working…" : "Dismiss"}
                      disabled={busyRecipe !== null}
                      onClick={() => void runAction(recommendation.recipeId, onDismiss!, true)}
                    />
                  </div>
                )}
                {event.action === "recommended" && !actionable && (
                  <p className="guardian-history-pending">This recommendation is no longer pending.</p>
                )}
                {actionStatus && busyRecipe === null && <p className="card-copy" style={{ margin: 0, fontSize: 11.5 }}>{actionStatus}</p>}
              </div>
            )}
          </div>
        })}
      </div>
    </div>
  );
}
