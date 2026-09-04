import { useEffect, useState } from "react";
import {
  fetchBootcSnapshot,
  fetchCollectAvailability,
  fetchPendingUpdatesSummary,
  fetchUpdateHealth,
  fetchUpdateStatus,
  fetchUpdaterAvailable,
  fetchUpdateWatcherStatus,
  setUpdateWatcherEnabled,
  checkForUpdatesNow,
  deferUpdateWatcher,
  invokeApplyStaged,
  invokeBootcRollback,
  invokeBootcUpgrade,
  confirmUserAction,
  type BootcSnapshot,
  type UpdateHealthLive,
  type UpdateStatusLive,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";
import { hubAcceptanceMode, recordHubAcceptance } from "../services/acceptance";
import { invoke } from "@tauri-apps/api/core";

type UpdateReadings = {
  snapshot: BootcSnapshot | null;
  status: UpdateStatusLive | null;
  pending: Record<string, string> | null;
  updater: boolean | null;
  health: UpdateHealthLive | null;
  watcher: Awaited<ReturnType<typeof fetchUpdateWatcherStatus>>;
};

const emptyReadings: UpdateReadings = { snapshot: null, status: null, pending: null, updater: null, health: null, watcher: null };

async function readUpdates(): Promise<UpdateReadings> {
  const [snapshot, status, pending, updater, health, watcher] = await Promise.all([
    fetchBootcSnapshot(),
    fetchUpdateStatus(),
    fetchPendingUpdatesSummary(),
    fetchUpdaterAvailable(),
    fetchUpdateHealth(),
    fetchUpdateWatcherStatus(),
  ]);
  return { snapshot, status, pending, updater, health, watcher };
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

  // Exercise one read-only update probe and the native validation failure
  // path in an installed-image run. The deliberately unknown operation can
  // never reach the privileged socket or mutate the guest.
  useEffect(() => {
    let cancelled = false;
    async function runAcceptanceProbes() {
      if (!(await hubAcceptanceMode()) || cancelled) return;
      try {
        const availability = await fetchCollectAvailability(null, false);
        if (!cancelled) {
          void recordHubAcceptance("updates-probe", JSON.stringify({ state: availability ? "ok" : "degraded", check_state: availability?.state ?? null }));
        }
      } catch (error) {
        if (!cancelled) void recordHubAcceptance("updates-probe", JSON.stringify({ state: "failed", detail: String(error) }));
      }
      try {
        await invoke("privileged_action", { operation: "acceptance-not-allowlisted", payload: {} });
        if (!cancelled) void recordHubAcceptance("privileged-failure", JSON.stringify({ state: "unexpected-success" }));
      } catch (error) {
        if (!cancelled) void recordHubAcceptance("privileged-failure", JSON.stringify({ state: "expected", detail: String(error) }));
      }
    }
    void runAcceptanceProbes();
    return () => { cancelled = true; };
  }, []);

  const { snapshot, status: updateStatus, pending, updater, health, watcher } = readings;
  const staged = updateStatus?.staged ?? false;
  const pendingCount = numericPending(pending);
  const updateReady = staged || updateStatus?.check_state === "available" || pendingCount > 0;
  const blocked = updateStatus?.check_state === "error" || Boolean(updateStatus?.blocked_reason) || health?.status === "unhealthy";
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
    const next = await readUpdates();
    const status = next.status ?? {
      booted: next.snapshot?.booted?.imageDigest ?? null,
      staged: false,
      rollback: Boolean(next.snapshot?.rollback),
      remote_digest: null,
      blocked_reason: null,
      retry_cmd: null,
      check_state: "idle",
      detail: "",
    };
    setReadings({
      ...next,
      status: {
        ...status,
        staged: availability.staged,
        check_state: availability.state,
        blocked_reason: availability.blocked_reason || null,
        detail: availability.detail,
      },
      pending: { ...(next.pending ?? {}), flatpak: String(availability.flatpak_count) },
    });
    setLoaded(true);
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

  async function setWatcherEnabled(enabled: boolean): Promise<string> {
    const detail = await setUpdateWatcherEnabled(enabled);
    await refresh();
    return detail;
  }

  async function checkWatcherNow(): Promise<string> {
    const detail = await checkForUpdatesNow();
    await refresh();
    return detail;
  }

  async function deferWatcher(): Promise<string> {
    const detail = await deferUpdateWatcher();
    await refresh();
    return detail;
  }

  const channel = snapshot?.channel ?? "Not identified";
  const version = snapshot?.booted?.version ?? snapshot?.booted?.image ?? "Not identified";
  const availabilityValue = !loaded ? "Checking…" : staged ? "Staged" : blocked ? "Check unavailable" : updateReady ? "Ready" : updateStatus?.check_state || "Not checked";
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
      {watcher && (
        <div className="updates-actions-card updates-watcher-card">
          <div>
            <span className="updates-eyebrow">Automatic updates</span>
            <h2>{watcher.available ? watcher.enabled ? "Automatic updates are enabled" : "Automatic updates are paused" : "Automatic updates unavailable"}</h2>
            <p>{watcher.available ? watcher.active ? "The update watcher timer is enabled and currently active." : "The watcher is installed but is not currently active." : "systemd could not be found on this system."}</p>
          </div>
          {watcher.available && (
            <div className="updates-actions">
              <ActionButton
                label={busy === "watcher-check" ? "Checking…" : "Check now"}
                disabled={busy !== null}
                onClick={() => confirmUserAction("Run the update watcher now? It may stage a system update and ask for authentication.") && void run("watcher-check", "Running the update watcher…", checkWatcherNow)}
              />
              <ActionButton
                label={busy === "watcher-toggle" ? "Updating…" : watcher.enabled ? "Disable automatic updates" : "Enable automatic updates"}
                disabled={busy !== null}
                onClick={() => confirmUserAction(`${watcher.enabled ? "Disable" : "Enable"} automatic updates?`) && void run("watcher-toggle", `${watcher.enabled ? "Disabling" : "Enabling"} automatic updates…`, () => setWatcherEnabled(!watcher.enabled))}
              />
              {watcher.enabled && (
                <ActionButton
                  label={busy === "watcher-defer" ? "Deferring…" : "Defer automatic updates"}
                  disabled={busy !== null}
                  onClick={() => confirmUserAction("Pause automatic updates until you enable them again?") && void run("watcher-defer", "Pausing automatic updates…", deferWatcher)}
                />
              )}
            </div>
          )}
        </div>
      )}
      <ActionStatus status={status} />
    </section>
  );
}
