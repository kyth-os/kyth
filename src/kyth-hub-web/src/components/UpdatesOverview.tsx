import { useEffect, useState } from "react";
import {
  checkForUpdates,
  fetchUpdatesSnapshot,
  invalidateSharedReads,
  invokeApplyStaged,
  invokeBootcRollback,
  invokeBootcUpgrade,
  updateFlatpaks,
  type UpdatesSnapshot,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";
import { friendlyActionError, friendlyActionResult, friendlyAvailabilityDetail, friendlyAvailabilityResult } from "./updateMessages";

type GuidanceTone = "ok" | "warn" | "muted";

type UpdateGuidance = {
  tone: GuidanceTone;
  icon: string;
  title: string;
  message: string;
  next: string;
  progress?: boolean;
};

const emptyReadings: UpdatesSnapshot = {
  snapshot: null,
  status: null,
  pending: null,
  health: null,
};

function numericPending(pending: Record<string, string> | null): number {
  const parsed = Number(pending?.flatpak ?? 0);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function actionErrorNextStep(failure: string, action: string | null): string {
  const lower = failure.toLowerCase();
  if (lower.includes("helper service isn't running") || lower.includes("system update helper isn't running")) {
    return "Update KythOS and restart, then choose “Try again”. Your current system is still safe to use.";
  }
  if (action === "check") {
    return "Check your connection, then choose “Try again”. Your current system is still safe to use.";
  }
  if (action === "apps") {
    return "Check your connection, then choose “Update apps” to try again.";
  }
  if (action === "apply") {
    return "Save your work, then restart from the system menu to finish applying the update.";
  }
  if (action === "rollback") {
    return "Choose “Roll back” again when you’re ready. Your current system is still safe to use.";
  }
  if (lower.includes("registry") || lower.includes("timed out") || lower.includes("network")) {
    return "Check that you are online, then choose “Try again”. Your current system is still safe to use.";
  }
  if (lower.includes("free disk space") || lower.includes("no space left")) {
    return "Free up some disk space, then choose “Download and stage” again.";
  }
  if (lower.includes("already in progress") || lower.includes("in progress") || lower.includes("locked")) {
    return "Wait for the other update to finish, then choose “Try again”.";
  }
  return "Choose “Download and stage” to try again. Your current system is still safe to use.";
}

export function UpdatesOverview() {
  const [readings, setReadings] = useState<UpdatesSnapshot>(emptyReadings);
  const [loaded, setLoaded] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const { status, busy, run } = useSectionAction();

  function startAction(id: string, pendingLabel: string, action: () => Promise<string>): void {
    setLastAction(id);
    void run(id, pendingLabel, action);
  }

  useEffect(() => {
    let cancelled = false;
    fetchUpdatesSnapshot().then((next) => {
      if (!cancelled) {
        setReadings(next);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function refresh(): Promise<string> {
    invalidateSharedReads(
      "updates-snapshot",
      "bootc-snapshot",
      "pending-updates",
      "update-status",
      "update-health",
      "probe:bootc-status-data",
      "probe:bootc-branch",
      "probe:flatpak-updates",
    );
    const next = await fetchUpdatesSnapshot();
    setReadings(next);
    setLoaded(true);
    return "Update status refreshed.";
  }

  async function check(): Promise<string> {
    try {
      const availability = await checkForUpdates();
      // The explicit check bypasses the normal read cache. Re-read the
      // inexpensive status fields so the page cannot show a stale staged
      // state or app count after a successful check.
      invalidateSharedReads(
        "updates-snapshot",
        "bootc-snapshot",
        "pending-updates",
        "update-status",
        "update-health",
        "probe:bootc-status-data",
        "probe:bootc-branch",
        "probe:flatpak-updates",
      );
      const next = await fetchUpdatesSnapshot();
      const currentStatus = next.status ?? {
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
          ...currentStatus,
          staged: availability.staged,
          check_state: availability.state,
          blocked_reason: availability.blocked_reason || null,
          detail: availability.detail,
        },
        pending: { ...(next.pending ?? {}), flatpak: String(availability.flatpak_count) },
      });
      setLoaded(true);
      return friendlyAvailabilityResult(availability.state, availability.staged, availability.detail);
    } catch (error) {
      throw new Error(friendlyActionError("check", error));
    }
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

  async function updateApps(): Promise<string> {
    try {
      const detail = await updateFlatpaks();
      await refresh();
      return detail;
    } catch (error) {
      throw new Error(friendlyActionError("apps", error));
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
    try {
      const detail = await invokeBootcRollback();
      await refresh();
      return friendlyActionResult("rollback", detail);
    } catch (error) {
      throw new Error(friendlyActionError("rollback", error));
    }
  }

  const { snapshot, status: updateStatus, pending, health } = readings;
  const staged = updateStatus?.staged ?? false;
  const pendingCount = numericPending(pending);
  const systemUpdateAvailable = updateStatus?.check_state === "available" && !staged;
  const checkFailed = updateStatus?.check_state === "error" || Boolean(updateStatus?.blocked_reason);
  const appUpdatesAvailable = pendingCount > 0;
  const hasReadings = snapshot !== null || updateStatus !== null || pending !== null || health !== null;
  const actionFailed = status?.startsWith("Failed:") ?? false;
  const canStage = !staged && (
    systemUpdateAvailable
    || checkFailed
    || (actionFailed && (lastAction === "check" || lastAction === "stage"))
  );
  const canRollback = Boolean(updateStatus?.rollback || snapshot?.rollback);

  const overallLabel = !loaded
    ? "Reading status"
    : staged
      ? "Restart required"
      : checkFailed
        ? "Check unavailable"
        : systemUpdateAvailable
          ? "Update available"
          : appUpdatesAvailable
            ? "App updates available"
            : updateStatus?.check_state === "uptodate"
              ? "Up to date"
              : hasReadings
                ? "Ready to check"
                : "Status unavailable";
  const overallTone: GuidanceTone = !loaded || !hasReadings
    ? "muted"
    : staged || systemUpdateAvailable || appUpdatesAvailable || checkFailed
      ? "warn"
      : "ok";

  const guidance: UpdateGuidance = (() => {
    if (busy === "check") {
      return {
        tone: "muted",
        icon: "⌕",
        title: "Checking for updates",
        message: "We’re checking KythOS for a newer version. This can take up to a minute on a slow connection.",
        next: "Keep this window open; we’ll show the result here.",
        progress: true,
      };
    }
    if (busy === "stage") {
      return {
        tone: "muted",
        icon: "↓",
        title: "Downloading and preparing your update",
        message: "KythOS is downloading the update and preparing it for your next restart. Your current system remains usable.",
        next: "Keep the Hub open until staging finishes.",
        progress: true,
      };
    }
    if (busy === "apps") {
      return {
        tone: "muted",
        icon: "↓",
        title: "Updating your apps",
        message: "Your app updates are downloading and installing now.",
        next: "Keep the Hub open until the app update finishes.",
        progress: true,
      };
    }
    if (busy === "apply") {
      return {
        tone: "muted",
        icon: "↻",
        title: "Restarting to finish the update",
        message: "KythOS is applying the staged update during the restart.",
        next: "Save any open work before the restart completes.",
      };
    }
    if (busy === "rollback") {
      return {
        tone: "muted",
        icon: "↶",
        title: "Preparing the rollback",
        message: "KythOS is selecting the previous system version for the next startup.",
        next: "The rollback takes effect after a restart.",
      };
    }
    if (actionFailed) {
      const failure = (status ?? "").replace(/^Failed:\s*/, "");
      return {
        tone: "warn",
        icon: "!",
        title: "The update could not be completed",
        message: failure,
        next: actionErrorNextStep(failure, lastAction),
      };
    }
    if (staged) {
      return {
        tone: "warn",
        icon: "✓",
        title: "Update ready — restart to finish",
        message: "The update has been downloaded and safely prepared for the next startup.",
        next: "Choose “Restart to apply” when you’re ready. Save open work first.",
      };
    }
    if (checkFailed) {
      return {
        tone: "warn",
        icon: "!",
        title: "We couldn’t check for updates",
        message: friendlyAvailabilityDetail(updateStatus?.blocked_reason || updateStatus?.detail, "The update service did not respond."),
        next: "Check your connection, then choose “Try again”.",
      };
    }
    if (systemUpdateAvailable) {
      return {
        tone: "warn",
        icon: "↓",
        title: "A KythOS update is available",
        message: "A newer system version is ready to download. Nothing changes until you choose to stage it.",
        next: "Choose “Download and stage”. We’ll tell you when a restart is needed.",
      };
    }
    if (appUpdatesAvailable) {
      return {
        tone: "warn",
        icon: "↓",
        title: "App updates are available",
        message: `${pendingCount} app update${pendingCount === 1 ? " is" : "s are"} waiting. KythOS itself is current.`,
        next: "Choose “Update apps” to install them.",
      };
    }
    if (!loaded) {
      return {
        tone: "muted",
        icon: "…",
        title: "Reading update status",
        message: "We’re reading the update information from this computer.",
        next: "Your next step will appear here shortly.",
      };
    }
    if (updateStatus?.check_state === "uptodate") {
      return {
        tone: "ok",
        icon: "✓",
        title: "You’re up to date",
        message: "KythOS is running the latest available system version.",
        next: "No action is needed. Check again whenever you like.",
      };
    }
    return {
      tone: "muted",
      icon: "↓",
      title: "Ready to check for updates",
      message: "We’ll look for a newer KythOS version and any app updates.",
      next: "Choose “Check for updates” to begin.",
    };
  })();

  const primaryAction = staged
    ? { id: "apply", label: busy === "apply" ? "Restarting…" : "Restart to apply", pending: "Applying the staged update…", action: apply }
    : systemUpdateAvailable
      ? { id: "stage", label: busy === "stage" ? "Downloading…" : actionFailed && lastAction === "stage" ? "Try again" : "Download and stage", pending: "Downloading and staging…", action: stage }
      : checkFailed
        ? { id: "check", label: busy === "check" ? "Checking…" : "Try again", pending: "Checking for updates…", action: check }
        : appUpdatesAvailable
          ? { id: "apps", label: busy === "apps" ? "Updating apps…" : actionFailed && lastAction === "apps" ? "Try again" : "Update apps", pending: "Updating your apps…", action: updateApps }
          : lastAction === "stage" && actionFailed
            ? { id: "stage", label: "Try again", pending: "Downloading and staging…", action: stage }
            : lastAction === "apps" && actionFailed
              ? { id: "apps", label: "Try again", pending: "Updating your apps…", action: updateApps }
              : { id: "check", label: busy === "check" ? "Checking…" : "Check for updates", pending: "Checking for updates…", action: check };

  const channel = snapshot?.channel ?? "Not identified";
  const version = snapshot?.booted?.version ?? snapshot?.booted?.image ?? "Not identified";
  const lastCheck = updateStatus?.detail && !checkFailed ? updateStatus.detail : "The latest check result will appear here.";

  return (
    <section className="updates-overview" aria-label="Updates overview">
      <div className={`updates-hero updates-hero-${overallTone}`}>
        <div>
          <span className="updates-eyebrow">System updates</span>
          <h1>Keep KythOS current</h1>
          <p>One place to check, stage, and finish system updates.</p>
          <div className="updates-meta" aria-label="Current system">
            <span>Channel <strong>{channel}</strong></span>
            <span>Version <strong>{version}</strong></span>
          </div>
        </div>
        <div className={`updates-ready-chip updates-chip-${overallTone}`}><span />{overallLabel}</div>
      </div>

      <div className={`updates-guidance updates-guidance-${guidance.tone}`} role="status" aria-live="polite" aria-busy={busy !== null}>
        <div className="updates-guidance-icon" aria-hidden="true">{guidance.icon}</div>
        <div className="updates-guidance-copy">
          <strong>{guidance.title}</strong>
          <p>{guidance.message}</p>
          <span>{guidance.next}</span>
          {guidance.progress && <div className="updates-guidance-progress" aria-label="Update operation in progress"><i /></div>}
        </div>
      </div>

      <div className="updates-actions-card updates-primary-actions">
        <div>
          <span className="updates-eyebrow">Next step</span>
          <h2>{staged ? "Finish the staged update" : systemUpdateAvailable ? "Install the available update" : appUpdatesAvailable ? "Update your apps" : "Update KythOS"}</h2>
          <p>{lastCheck}</p>
        </div>
        <div className="updates-actions">
          <ActionButton
            primary
            label={primaryAction.label}
            disabled={busy !== null || !loaded}
            onClick={() => startAction(primaryAction.id, primaryAction.pending, primaryAction.action)}
          />
          {canStage && primaryAction.id !== "stage" && (
            <ActionButton
              label={busy === "stage" ? "Downloading…" : "Download and stage"}
              disabled={busy !== null || !loaded}
              onClick={() => startAction("stage", "Downloading and staging…", stage)}
            />
          )}
          {appUpdatesAvailable && primaryAction.id !== "apps" && (
            <ActionButton
              label={busy === "apps" ? "Updating apps…" : "Update apps"}
              disabled={busy !== null || !loaded}
              onClick={() => startAction("apps", "Updating your apps…", updateApps)}
            />
          )}
          {canRollback && (
            <ActionButton
              label={busy === "rollback" ? "Rolling back…" : "Roll back"}
              disabled={busy !== null || !loaded}
              onClick={() => startAction("rollback", "Preparing rollback…", rollback)}
            />
          )}
        </div>
        <ActionStatus status={status} />
      </div>

      <details className="updates-details">
        <summary>System details and recovery</summary>
        <div className="updates-details-grid">
          <div><span>Update health</span><strong>{health?.status ?? "Not checked"}</strong></div>
          <div><span>Rollback</span><strong>{canRollback ? "Available" : "Not available"}</strong></div>
          <div><span>App updates</span><strong>{pendingCount > 0 ? `${pendingCount} available` : "None found"}</strong></div>
          <div><span>Last result</span><strong>{friendlyAvailabilityDetail(lastCheck, "Not checked yet.")}</strong></div>
        </div>
      </details>
    </section>
  );
}
