import { useEffect, useState } from "react";
import {
  fetchBootcSnapshot,
  fetchCollectAvailability,
  fetchPendingUpdatesSummary,
  fetchUpdateHealth,
  fetchUpdateStatus,
  fetchUpdaterAvailable,
  invokeApplyStaged,
  invokeBootcRollback,
  invokeBootcUpgrade,
  type BootcSnapshot,
  type UpdateHealthLive,
  type UpdateStatusLive,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

type UpdateReadings = {
  snapshot: BootcSnapshot | null;
  status: UpdateStatusLive | null;
  pending: Record<string, string> | null;
  updater: boolean | null;
  health: UpdateHealthLive | null;
};

const emptyReadings: UpdateReadings = { snapshot: null, status: null, pending: null, updater: null, health: null };

async function readUpdates(): Promise<UpdateReadings> {
  const [snapshot, status, pending, updater, health] = await Promise.all([
    fetchBootcSnapshot(),
    fetchUpdateStatus(),
    fetchPendingUpdatesSummary(),
    fetchUpdaterAvailable(),
    fetchUpdateHealth(),
  ]);
  return { snapshot, status, pending, updater, health };
}

type CardTone = "ok" | "warn" | "muted";

function UpdateCard({ icon, label, value, detail, tone }: {
  icon: string;
  label: string;
  value: string;
  detail: string;
  tone: CardTone;
}) {
  return (
    <article className={`updates-card updates-card-${tone}`}>
      <div className="updates-card-top">
        <span className="updates-card-icon" aria-hidden="true">{icon}</span>
        <span className="updates-card-label">{label}</span>
        <span className={`updates-status-dot updates-status-${tone}`} />
      </div>
      <strong className="updates-card-value">{value}</strong>
      <span className="updates-card-detail">{detail}</span>
    </article>
  );
}

function numericPending(pending: Record<string, string> | null): number {
  if (!pending) return 0;
  return Object.values(pending).reduce((total, value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? total + parsed : total;
  }, 0);
}

export function UpdatesOverview() {
  const [readings, setReadings] = useState<UpdateReadings>(emptyReadings);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    readUpdates().then((next) => {
      if (!cancelled) {
        setReadings(next);
        setLoaded(true);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const { snapshot, status: updateStatus, pending, updater, health } = readings;
  const staged = updateStatus?.staged ?? false;
  const pendingCount = numericPending(pending);
  const updateReady = staged || updateStatus?.check_state === "available" || pendingCount > 0;
  const blocked = Boolean(updateStatus?.blocked_reason) || health?.status === "unhealthy";
  const healthNeedsAttention = health !== null && health.status !== "healthy";
  const hasReadings = snapshot !== null || updateStatus !== null || pending !== null || health !== null;
  const overallLabel = !loaded ? "Checking updates" : blocked || healthNeedsAttention ? "Needs attention" : staged ? "Restart to finish" : updateReady ? "Update ready" : hasReadings ? "System is current" : "Status unavailable";
  const overallTone: CardTone = !loaded || !hasReadings ? "muted" : blocked || healthNeedsAttention || updateReady ? "warn" : "ok";

  async function refresh(): Promise<string> {
    const next = await readUpdates();
    setReadings(next);
    setLoaded(true);
    return "Update status refreshed.";
  }

  async function check(): Promise<string> {
    const availability = await fetchCollectAvailability(null, false);
    if (!availability) return "Update checking is not available outside the Hub shell.";
    await refresh();
    return availability.detail;
  }

  async function stage(): Promise<string> {
    const detail = await invokeBootcUpgrade();
    await refresh();
    return detail;
  }

  async function apply(): Promise<string> {
    const detail = await invokeApplyStaged();
    await refresh();
    return detail;
  }

  async function rollback(): Promise<string> {
    const detail = await invokeBootcRollback();
    await refresh();
    return detail;
  }

  const channel = snapshot?.channel ?? "Not identified";
  const version = snapshot?.booted?.version ?? "Not identified";
  const availabilityValue = !loaded ? "Checking…" : staged ? "Staged" : updateReady ? "Ready" : updateStatus?.check_state || "Not checked";
  const availabilityDetail = updateStatus?.blocked_reason || updateStatus?.detail || (pendingCount > 0 ? `${pendingCount} update item${pendingCount === 1 ? "" : "s"} reported.` : "Check now to query the update source.");
  const healthValue = health?.status ?? "Not checked";
  const healthDetail = health?.detail || "Boot health is checked after an image is deployed.";
  const recoveryValue = updateStatus?.rollback || snapshot?.rollback ? "Rollback available" : "No rollback";
  const recoveryDetail = snapshot?.rollback?.version ? `Previous image ${snapshot.rollback.version} is ready.` : "A rollback appears after a deployment has been recorded.";

  return (
    <section className="updates-overview" aria-label="Updates overview">
      <div className={`updates-hero updates-hero-${overallTone}`}>
        <div>
          <span className="updates-eyebrow">System updates</span>
          <h1>Keep KythOS current</h1>
          <p>See what is ready, stage updates safely, and recover from a bad deployment without leaving the Hub.</p>
        </div>
        <div className={`updates-ready-chip updates-chip-${overallTone}`}><span />{overallLabel}</div>
      </div>

      <div className="updates-card-grid">
        <UpdateCard icon="◈" label="Update channel" value={channel} detail="The release stream this device follows." tone={snapshot ? "ok" : "muted"} />
        <UpdateCard icon="▣" label="Current version" value={version} detail={snapshot?.booted?.timestamp ? `Booted ${snapshot.booted.timestamp}.` : "The booted image has not been read yet."} tone={snapshot?.booted ? "ok" : "muted"} />
        <UpdateCard icon="↓" label="Availability" value={availabilityValue} detail={availabilityDetail} tone={blocked || updateReady ? "warn" : updateStatus ? "ok" : "muted"} />
        <UpdateCard icon="✓" label="Update health" value={healthValue} detail={healthDetail} tone={health ? health.status === "healthy" ? "ok" : "warn" : "muted"} />
        <UpdateCard icon="↶" label="Recovery" value={recoveryValue} detail={recoveryDetail} tone={updateStatus?.rollback || snapshot?.rollback ? "ok" : snapshot || updateStatus ? "muted" : "muted"} />
      </div>

      <div className="updates-actions-card">
        <div>
          <span className="updates-eyebrow">Update controls</span>
          <h2>{updater === false ? "Background updater is unavailable" : "Choose what happens next"}</h2>
          <p>Every action reports progress here and uses the native update bridge.</p>
        </div>
        <div className="updates-actions">
          <ActionButton label={busy === "check" ? "Checking…" : "Check for updates"} disabled={busy !== null} onClick={() => void run("check", "Checking for updates…", check)} />
          <ActionButton label={busy === "stage" ? "Downloading…" : "Download and stage"} disabled={busy !== null || blocked} onClick={() => void run("stage", "Downloading and staging…", stage)} />
          {staged && <ActionButton label={busy === "apply" ? "Restarting…" : "Restart to apply"} disabled={busy !== null} onClick={() => void run("apply", "Applying the staged update…", apply)} />}
          {(updateStatus?.rollback || snapshot?.rollback) && <ActionButton label={busy === "rollback" ? "Rolling back…" : "Roll back"} disabled={busy !== null} onClick={() => void run("rollback", "Rolling back…", rollback)} />}
          <ActionButton label={busy === "refresh" ? "Refreshing…" : "Refresh status"} disabled={busy !== null} onClick={() => void run("refresh", "Refreshing update status…", refresh)} />
        </div>
      </div>
      <ActionStatus status={status} />
    </section>
  );
}
