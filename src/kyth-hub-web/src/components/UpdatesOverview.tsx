import { useEffect, useState } from "react";
import {
  cancelInstall,
  cancelUpdateJob,
  checkForUpdates,
  fetchStageProgress,
  fetchUpdatesSnapshot,
  getInFlightJob,
  invalidateSharedReads,
  invokeApplyStaged,
  invokeBootcRollback,
  invokeBootcUpgrade,
  updateFlatpaks,
  type StageProgress,
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
  progressPct?: number;
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
  const { status, busy, run } = useSectionAction("update");
  // A tracked backend job survives reloads (reattached from storage) but
  // component state does not — mirror the slots so Cancel and the running
  // guidance stay available even when this mount never launched anything.
  const [updateTracked, setUpdateTracked] = useState(() => getInFlightJob("update") !== undefined);
  const [cancelling, setCancelling] = useState(false);
  const [cancelNote, setCancelNote] = useState<string | null>(null);
  // Latch a successful stage locally: the staged deployment exists the
  // moment the job completes, even if the next status probe has not caught
  // up yet. The latch clears as soon as the backend confirms staged (or a
  // rollback/apply changes the state again).
  const [stagedLatch, setStagedLatch] = useState(false);
  const [stageProgress, setStageProgress] = useState<StageProgress | null>(null);

  // While a stage runs, poll the live byte/layer progress for the
  // determinate bar. Stops with the job; the last reading stays rendered
  // until the page refreshes into the staged state.
  useEffect(() => {
    if (busy !== "stage") return;
    let stopped = false;
    const tick = async () => {
      try {
        const next = await fetchStageProgress();
        if (!stopped && next && next.active) setStageProgress(next);
      } catch { /* keep the last reading; the job poll owns errors */ }
    };
    void tick();
    const timer = window.setInterval(tick, 1000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [busy]);

  function syncTrackedJobs(): void {
    setUpdateTracked(getInFlightJob("update") !== undefined);
  }

  function startAction(id: string, pendingLabel: string, action: () => Promise<string>): void {
    setLastAction(id);
    setCancelNote(null);
    if (id === "stage" || id === "apply" || id === "rollback") setUpdateTracked(true);
    void run(id, pendingLabel, action).finally(syncTrackedJobs);
  }

  // Cancel never routes through `run`: the buttons above stay disabled while
  // `busy`, and Cancel must stay enabled exactly then.
  async function cancelRunning(kind: "update" | "apps"): Promise<void> {
    const localRunActive = busy !== null;
    setCancelling(true);
    setCancelNote("Cancelling…");
    try {
      const result = kind === "update" ? await cancelUpdateJob() : await cancelInstall();
      if (result === "Nothing to cancel.") {
        setCancelNote("There is no running update to cancel.");
      } else if (localRunActive) {
        // The local run is still polling the same job: its settle message
        // (e.g. the honest cancelled-stage text) lands as the action status,
        // so don't pin the raw result here too.
        setCancelNote(null);
      } else if (result === "Cancelled.") {
        setCancelNote("The update was cancelled. The status above is refreshed — follow whatever it offers next.");
      } else {
        setCancelNote(result);
      }
    } catch (error) {
      setCancelNote(`Failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      syncTrackedJobs();
      setCancelling(false);
      await refresh().catch(() => undefined);
    }
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
    // The backend caught up with the staged deployment: the local latch
    // hands over to live data.
    if (next.status?.staged) setStagedLatch(false);
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
      // The job completed: the deployment is staged even if the next
      // probe has not caught up. Latch the staged UI now; refresh hands
      // back to live data as soon as the backend confirms.
      setStagedLatch(true);
      setStageProgress(null);
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
      setStagedLatch(false);
      await refresh();
      return friendlyActionResult("apply", detail);
    } catch (error) {
      throw new Error(friendlyActionError("apply", error));
    }
  }

  async function rollback(): Promise<string> {
    try {
      const detail = await invokeBootcRollback();
      setStagedLatch(false);
      await refresh();
      return friendlyActionResult("rollback", detail);
    } catch (error) {
      throw new Error(friendlyActionError("rollback", error));
    }
  }

  const { snapshot, status: updateStatus, pending, health } = readings;
  const staged = updateStatus?.staged ?? false;
  // Latched staged state wins until the backend confirms it: right after a
  // successful stage the primary button must read "Restart to apply", not
  // fall back to "Check for updates" on a lagging probe.
  const stagedEffective = staged || stagedLatch;
  const pendingCount = numericPending(pending);
  const systemUpdateAvailable = updateStatus?.check_state === "available" && !stagedEffective;
  // "blocked" (e.g. a quarantined update held back for safety) and "busy"
  // (a mutating operation in flight) are backend states, not read failures:
  // neither may render as up-to-date nor as a connection error.
  const isBlocked = updateStatus?.check_state === "blocked";
  const backendBusy = updateStatus?.check_state === "busy";
  const checkFailed = updateStatus?.check_state === "error" || (Boolean(updateStatus?.blocked_reason) && !isBlocked);
  const appUpdatesAvailable = pendingCount > 0;
  const hasReadings = snapshot !== null || updateStatus !== null || pending !== null || health !== null;
  const actionFailed = status?.startsWith("Failed:") ?? false;
  const canStage = !stagedEffective && !isBlocked && (
    systemUpdateAvailable
    || checkFailed
    || (actionFailed && (lastAction === "check" || lastAction === "stage"))
  );
  const canRollback = Boolean(updateStatus?.rollback || snapshot?.rollback);

  const overallLabel = !loaded
    ? "Reading status"
    : staged
      ? "Restart required"
      : backendBusy
        ? "Update in progress"
        : isBlocked
          ? "Update blocked"
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
  const overallTone: GuidanceTone = !loaded || !hasReadings || backendBusy
    ? "muted"
    : staged || systemUpdateAvailable || appUpdatesAvailable || checkFailed || isBlocked
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
      // Determinate while markers stream; indeterminate before the first
      // one lands (sudo prompt, preflight) or on an older helper.
      const live = stageProgress?.active === true && stageProgress.pct > 0 ? stageProgress : null;
      return {
        tone: "muted",
        icon: "↓",
        title: live?.phase === "install" ? "Installing your update" : "Downloading and preparing your update",
        message: live?.detail ?? "KythOS is downloading the update and preparing it for your next restart. Your current system remains usable.",
        next: live ? `${live.pct}% complete. Keep the Hub open until staging finishes.` : "Keep the Hub open until staging finishes.",
        progress: true,
        progressPct: live?.pct,
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
    if (backendBusy) {
      return {
        tone: "muted",
        icon: "↓",
        title: "An update operation is in progress",
        message: updateStatus?.detail || "A system update operation is running on this computer.",
        next: updateTracked
          ? "It will finish on its own; you can also choose “Cancel update” below to stop it."
          : "It will finish on its own. Your current system stays usable meanwhile.",
        progress: true,
      };
    }
    if (busy === null && updateTracked && !stagedEffective) {
      return {
        tone: "muted",
        icon: "↓",
        title: "An update is still running",
        message: "A previous update action is still running in the background. Its progress resumes here.",
        next: "You can wait for it to finish or choose “Cancel update” below to stop it.",
        progress: true,
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
    if (stagedEffective) {
      return {
        tone: "warn",
        icon: "✓",
        title: "Update ready — restart to finish",
        message: "The update has been downloaded and safely prepared for the next startup.",
        next: "Choose “Restart to apply” when you’re ready. Save open work first.",
      };
    }
    if (isBlocked) {
      return {
        tone: "warn",
        icon: "!",
        title: "This update is blocked",
        message: updateStatus?.blocked_reason || updateStatus?.detail || "The update was held back for safety.",
        next: "Your system stays on its current version. Open Repair to review the blocked update, or choose “Check for updates” to look again.",
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

  const primaryAction = stagedEffective
    ? { id: "apply", label: busy === "apply" ? "Restarting…" : "Restart to apply", pending: "Applying the staged update…", action: apply }
    : isBlocked
      ? { id: "check", label: busy === "check" ? "Checking…" : "Check for updates", pending: "Checking for updates…", action: check }
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
  // Update-domain jobs (stage/apply/rollback/switch) are cancellable while
  // running — including a job reattached after a reload, which has no local
  // `busy` anymore. App updates run in the install domain instead.
  const showUpdateCancel = busy === "stage" || busy === "apply" || busy === "rollback" || (busy === null && updateTracked);

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
          {guidance.progress && (guidance.progressPct !== undefined
            ? <div className="updates-guidance-progress updates-guidance-progress-determinate" role="progressbar" aria-valuenow={guidance.progressPct} aria-valuemin={0} aria-valuemax={100} aria-label="Update download and staging progress"><i style={{ width: `${guidance.progressPct}%` }} /></div>
            : <div className="updates-guidance-progress" aria-label="Update operation in progress"><i /></div>)}
        </div>
      </div>

      <div className="updates-actions-card updates-primary-actions">
        <div>
          <span className="updates-eyebrow">Next step</span>
          <h2>{stagedEffective ? "Finish the staged update" : systemUpdateAvailable ? "Install the available update" : appUpdatesAvailable ? "Update your apps" : "Update KythOS"}</h2>
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
          {showUpdateCancel && (
            <ActionButton
              label={cancelling ? "Cancelling…" : "Cancel update"}
              disabled={cancelling || !loaded}
              onClick={() => void cancelRunning("update")}
            />
          )}
          {busy === "apps" && (
            <ActionButton
              label={cancelling ? "Cancelling…" : "Cancel"}
              disabled={cancelling || !loaded}
              onClick={() => void cancelRunning("apps")}
            />
          )}
        </div>
        <ActionStatus status={cancelNote ?? status} />
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
