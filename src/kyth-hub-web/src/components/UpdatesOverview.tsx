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
import { ActionButton, useSectionAction } from "./SectionActions";
import { hubAcceptanceMode, recordHubAcceptance } from "../services/acceptance";
import { invoke } from "@tauri-apps/api/core";
import { friendlyActionError, friendlyActionResult, friendlyAvailabilityDetail, friendlyAvailabilityResult } from "./updateMessages";

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

type GuidanceTone = "ok" | "warn" | "muted";

type UpdateGuidance = {
  tone: GuidanceTone;
  icon: string;
  title: string;
  message: string;
  next: string;
  progress?: boolean;
};

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
  const systemUpdateAvailable = updateStatus?.check_state === "available" && !staged;
  const appUpdatesAvailable = pendingCount > 0;
  const updateReady = staged || systemUpdateAvailable || appUpdatesAvailable;
  const blocked = updateStatus?.check_state === "error" || Boolean(updateStatus?.blocked_reason) || health?.status === "unhealthy";
  const healthNeedsAttention = health !== null && health.status !== "healthy";
  const hasReadings = snapshot !== null || updateStatus !== null || pending !== null || health !== null;
  const overallLabel = !loaded ? "Checking updates" : blocked || healthNeedsAttention ? "Needs attention" : staged ? "Restart to finish" : systemUpdateAvailable ? "Update available" : appUpdatesAvailable ? "App updates available" : hasReadings ? "You're up to date" : "Status unavailable";
  const overallTone: CardTone = !loaded || !hasReadings ? "muted" : blocked || healthNeedsAttention || updateReady ? "warn" : "ok";

  async function refresh(): Promise<string> {
    const next = await readUpdates();
    setReadings(next);
    setLoaded(true);
    return "Update status refreshed.";
  }

  async function check(): Promise<string> {
    const availability = await fetchCollectAvailability(null, false);
    if (!availability) return "Update checking is only available in the installed Hub.";
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
    return friendlyAvailabilityResult(availability.state, availability.staged, availability.detail);
  }

  async function stage(): Promise<string> {
    try {
      const detail = await invokeBootcUpgrade();
      await refresh();
      return friendlyActionResult("stage", detail);
    } catch (error) {
      throw new Error(friendlyActionError("stage", error));
    }
  }

  async function apply(): Promise<string> {
    try {
      const detail = await invokeApplyStaged();
      await refresh();
      return friendlyActionResult("apply", detail);
    } catch (error) {
      throw new Error(friendlyActionError("apply", error));
    }
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
  const availabilityValue = !loaded ? "Checking…" : staged ? "Restart required" : blocked ? "Check unavailable" : systemUpdateAvailable ? "Update available" : appUpdatesAvailable ? "Apps have updates" : updateStatus?.check_state === "uptodate" ? "Up to date" : "Not checked";
  const availabilityDetail = staged
    ? "Downloaded and ready to finish."
    : blocked
      ? friendlyAvailabilityDetail(updateStatus?.blocked_reason || updateStatus?.detail, "The update check needs attention. Try again when you're online.")
      : systemUpdateAvailable
        ? "A newer KythOS update is ready to download."
        : appUpdatesAvailable
          ? `${pendingCount} app update${pendingCount === 1 ? "" : "s"} available.`
          : updateStatus?.check_state === "uptodate"
            ? "No KythOS update is waiting to be installed."
            : "Check now to see whether a newer KythOS update is available.";
  const healthValue = health?.status ?? "Not checked";
  const healthDetail = health
    ? health.status === "healthy"
      ? "KythOS checked the last startup successfully."
      : "KythOS found an issue after the last startup. See Update health for details."
    : "KythOS checks system health after an update is applied.";
  const recoveryValue = updateStatus?.rollback || snapshot?.rollback ? "Rollback available" : "No rollback";
  const recoveryDetail = snapshot?.rollback?.version ? `Previous image ${snapshot.rollback.version} is ready.` : "A rollback appears after a deployment has been recorded.";

  const guidance: UpdateGuidance = (() => {
    if (busy === "check") {
      return { tone: "muted", icon: "⌕", title: "Checking for updates", message: "We’re checking KythOS for a newer version. This usually takes a moment.", next: "You can keep this window open while we check." };
    }
    if (busy === "stage") {
      return { tone: "muted", icon: "↓", title: "Downloading and preparing your update", message: "KythOS is downloading the update and preparing it for the next restart. This may take a few minutes.", next: "Keep the Hub open until the update is ready.", progress: true };
    }
    if (busy === "apply") {
      return { tone: "muted", icon: "↻", title: "Restarting to finish the update", message: "KythOS is restarting now. The update will finish installing during the restart.", next: "Save your work if anything else is open." };
    }
    if (busy === "rollback") {
      return { tone: "muted", icon: "↶", title: "Preparing the rollback", message: "KythOS is switching the next startup to the previous system image.", next: "The change takes effect after the restart." };
    }
    if (busy === "refresh" || busy === "watcher-check") {
      return { tone: "muted", icon: "↻", title: "Refreshing update status", message: "We’re reading the latest update information from this computer.", next: "The next step will appear here when the check finishes." };
    }
    if (status?.startsWith("Failed:")) {
      return { tone: "warn", icon: "!", title: "The update could not be completed", message: status.replace(/^Failed:\s*/, ""), next: "Check your connection and try again." };
    }
    if (staged) {
      return { tone: "warn", icon: "✓", title: "Update ready — restart to finish", message: "The update has been downloaded and installed safely for the next startup.", next: "Choose “Restart to apply” when you’re ready. Save any open work first." };
    }
    if (blocked || healthNeedsAttention) {
      return { tone: "warn", icon: "!", title: "Update check needs attention", message: "We couldn’t confirm the latest update status right now.", next: "Check your internet connection, then choose “Check for updates” to try again." };
    }
    if (systemUpdateAvailable) {
      return { tone: "warn", icon: "↓", title: "A KythOS update is available", message: "A newer system version is ready to download. Your current system will keep working while it downloads.", next: "Choose “Download and stage”. We’ll tell you when a restart is needed." };
    }
    if (appUpdatesAvailable) {
      return { tone: "warn", icon: "↓", title: "App updates are available", message: `${pendingCount} app update${pendingCount === 1 ? " is" : "s are"} waiting. Your KythOS system itself is current.`, next: "Update apps from the Apps page." };
    }
    if (!loaded) {
      return { tone: "muted", icon: "…", title: "Reading update status", message: "We’re checking this computer’s update status.", next: "Your next step will appear here shortly." };
    }
    if (updateStatus?.check_state === "uptodate") {
      return { tone: "ok", icon: "✓", title: "You’re up to date", message: "KythOS is running the latest available system update.", next: "No action is needed. Check again whenever you like." };
    }
    return { tone: "muted", icon: "↓", title: "Check for updates", message: "Find out whether a newer KythOS version is available.", next: "Choose “Check for updates” to begin." };
  })();

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

      <div className={`updates-guidance updates-guidance-${guidance.tone}`} role="status" aria-live="polite">
        <div className="updates-guidance-icon" aria-hidden="true">{guidance.icon}</div>
        <div className="updates-guidance-copy">
          <strong>{guidance.title}</strong>
          <p>{guidance.message}</p>
          <span>{guidance.next}</span>
          {guidance.progress && <div className="updates-guidance-progress" aria-label="Update download in progress"><i /></div>}
        </div>
      </div>

      <div className="updates-actions-card">
        <div>
          <span className="updates-eyebrow">Update controls</span>
          <h2>{updater === false ? "Background updater is unavailable" : "Choose what happens next"}</h2>
          <p>We’ll explain what’s happening and tell you what to do next.</p>
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
    </section>
  );
}
