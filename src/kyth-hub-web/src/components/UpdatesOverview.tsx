import { useEffect, useState } from "react";
import {
  cancelUpdateJob,
  checkForUpdates,
  fetchStageProgress,
  fetchUpdatesSnapshot,
  getInFlightJob,
  invalidateSharedReads,
  invokeApplyStaged,
  invokeBootcRollback,
  invokeBootcUpgrade,
  type StageProgress,
  type UpdatesSnapshot,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";
import { friendlyActionError, friendlyActionNextStep, friendlyActionResult, friendlyAvailabilityDetail, friendlyAvailabilityResult } from "./updateMessages";

type GuidanceTone = "ok" | "warn" | "muted";
type UpdatePhase = "prepare" | "download" | "install" | "verify" | "finalize";

const updatePhases: { id: UpdatePhase; label: string }[] = [
  { id: "prepare", label: "Prepare" },
  { id: "download", label: "Download" },
  { id: "install", label: "Install" },
  { id: "verify", label: "Verify" },
  { id: "finalize", label: "Ready" },
];

function updatePhaseIndex(phase: string | undefined): number {
  const index = updatePhases.findIndex((item) => item.id === phase);
  return index < 0 ? 1 : index;
}

function recognizedUpdatePhase(phase: string | undefined): UpdatePhase | undefined {
  return updatePhases.find((item) => item.id === phase)?.id;
}

function updatePhaseTitle(phase: string | undefined): string {
  switch (phase) {
    case "prepare": return "Preparing your update";
    case "download": return "Downloading your update";
    case "install": return "Installing your update";
    case "verify": return "Verifying your update";
    case "finalize": return "Finalizing your update";
    default: return "Updating your system";
  }
}

type UpdateGuidance = {
  tone: GuidanceTone;
  icon: string;
  title: string;
  message: string;
  next: string;
  progress?: boolean;
  progressPct?: number;
  phase?: UpdatePhase;
  phaseComplete?: boolean;
};

const emptyReadings: UpdatesSnapshot = {
  snapshot: null,
  status: null,
  pending: null,
  health: null,
};

// UpdatesOverview owns the system (bootc) update workflow only — check,
// download/stage, restart to apply, and rollback. App (Flatpak) updates
// moved to the Apps page's App Store section, which owns its own pending
// count, action, and error messaging so the two workflows cannot bleed
// into each other's status or busy state.
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
  // determinate bar. The backend-tracked job survives a frontend reload
  // (reattached from storage), so poll for that too — otherwise the bar
  // drops back to indeterminate after a reload mid-stage. Readings apply
  // while active or still advancing; the bar never moves backwards.
  const stagePollActive =
    busy === "stage" || (updateTracked && !(readings.status?.staged || stagedLatch));
  useEffect(() => {
    if (!stagePollActive) return;
    let stopped = false;
    const tick = async () => {
      try {
        const next = await fetchStageProgress();
        if (stopped || !next) return;
        setStageProgress((prev) => {
          if (next.active || next.pct > (prev?.pct ?? 0)) return next;
          return prev;
        });
      } catch { /* keep the last reading; the job poll owns errors */ }
    };
    void tick();
    const timer = window.setInterval(tick, 1000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [stagePollActive, busy, updateTracked, readings.status?.staged, stagedLatch]);

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
  async function cancelRunning(): Promise<void> {
    const localRunActive = busy !== null;
    setCancelling(true);
    setCancelNote("Cancelling…");
    try {
      const result = await cancelUpdateJob();
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
      "update-status",
      "update-health",
      "probe:bootc-status-data",
      "probe:bootc-branch",
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
      // state after a successful check.
      invalidateSharedReads(
        "updates-snapshot",
        "bootc-snapshot",
        "update-status",
        "update-health",
        "probe:bootc-status-data",
        "probe:bootc-branch",
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
      });
      setLoaded(true);
      // The same backend check also refreshes the app update count as a
      // side effect (collect_availability fans out to both); the App Store
      // section reads its own pending-updates cache independently and picks
      // that up on its next poll rather than depending on this page.
      invalidateSharedReads("pending-updates", "probe:flatpak-updates");
      return friendlyAvailabilityResult(availability.state, availability.staged, availability.detail);
    } catch (error) {
      throw new Error(friendlyActionError("check", error));
    }
  }

  async function stage(): Promise<string> {
    let detail: string;
    try {
      detail = await invokeBootcUpgrade();
    } catch (error) {
      // A helper can stage successfully and then fail while reporting or
      // finalizing. Refresh authoritative state before telling the user to retry.
      try {
        invalidateSharedReads(
          "updates-snapshot",
          "bootc-snapshot",
          "update-status",
          "update-health",
          "probe:bootc-status-data",
          "probe:bootc-branch",
        );
        const next = await fetchUpdatesSnapshot();
        setReadings(next);
        setLoaded(true);
        if (next.status?.staged) {
          setStagedLatch(true);
          setStageProgress(null);
          return friendlyActionResult("stage", "Update staged and promoted to the next boot.");
        }
      } catch { /* keep the original stage error; its detail is more useful */ }
      throw new Error(friendlyActionError("stage", error));
    }
    // The stage job itself succeeded. Do not reclassify it as failed if the
    // follow-up status refresh is temporarily unavailable; the latch keeps
    // the next action at Restart to apply.
    setStagedLatch(true);
    setStageProgress(null);
    await refresh().catch(() => undefined);
    return friendlyActionResult("stage", detail);
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

  const { snapshot, status: updateStatus, health } = readings;
  const staged = updateStatus?.staged ?? false;
  // Latched staged state wins until the backend confirms it: right after a
  // successful stage the primary button must read "Restart to apply", not
  // fall back to "Check for updates" on a lagging probe.
  const stagedEffective = staged || stagedLatch;
  const systemUpdateAvailable = updateStatus?.check_state === "available" && !stagedEffective;
  // "blocked" (e.g. a quarantined update held back for safety) and "busy"
  // (a mutating operation in flight) are backend states, not read failures:
  // neither may render as up-to-date nor as a connection error.
  const isBlocked = updateStatus?.check_state === "blocked";
  const stagingInProgress = updateTracked && stageProgress?.active === true;
  const backendBusy = updateStatus?.check_state === "busy" || stagingInProgress;
  const checkFailed = updateStatus?.check_state === "error" || (Boolean(updateStatus?.blocked_reason) && !isBlocked);
  const hasReadings = snapshot !== null || updateStatus !== null || health !== null;
  const actionFailed = status?.startsWith("Failed:") ?? false;
  const canStage = !stagedEffective && !isBlocked && (
    systemUpdateAvailable
    || checkFailed
    || (actionFailed && (lastAction === "check" || lastAction === "stage"))
  );
  const canRollback = Boolean(updateStatus?.rollback || snapshot?.rollback);

  const overallLabel = !loaded
    ? "Reading status"
    : stagedEffective
      ? "Restart required"
      : backendBusy
        ? "Update in progress"
        : isBlocked
          ? "Update blocked"
          : checkFailed
            ? "Check unavailable"
            : systemUpdateAvailable
              ? "Update available"
              : updateStatus?.check_state === "uptodate"
                ? "Up to date"
                : hasReadings
                  ? "Ready to check"
                  : "Status unavailable";
  const overallTone: GuidanceTone = !loaded || !hasReadings || backendBusy
    ? "muted"
    : stagedEffective || systemUpdateAvailable || checkFailed || isBlocked
      ? "warn"
      : "ok";
  const systemStatusLabel = !loaded
    ? "Not checked"
    : stagedEffective
      ? "Restart required"
      : backendBusy
        ? "In progress"
        : isBlocked
          ? "Blocked"
          : checkFailed
            ? "Check unavailable"
            : systemUpdateAvailable
              ? "Update available"
              : updateStatus?.check_state === "uptodate"
                ? "Up to date"
                : "Ready to check";
  const systemStatusDetail = stagedEffective
    ? "The system update is prepared for your next boot."
    : backendBusy
      ? stageProgress?.active
        ? stageProgress.detail
        : "A system update operation is in progress. Your current system remains usable."
    : systemUpdateAvailable
      ? "A newer KythOS version is ready to stage."
      : isBlocked
        ? updateStatus?.blocked_reason || "The update is held for safety."
        : checkFailed
          ? "The latest system check needs attention."
          : updateStatus?.check_state === "uptodate"
            ? "No system restart is needed."
            : "Check to see whether a system update is available.";
  const systemStatusTone: GuidanceTone = backendBusy
    ? "muted"
    : stagedEffective || systemUpdateAvailable || isBlocked || checkFailed
    ? "warn"
    : updateStatus?.check_state === "uptodate" ? "ok" : "muted";

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
      // Keep the preparing state visible before the first layer arrives;
      // switch to a determinate bar as soon as the helper reports a percent.
      const live = stageProgress?.active === true ? stageProgress : null;
      const hasPercent = live !== null && live.pct > 0;
      return {
        tone: "muted",
        icon: "↓",
        title: updatePhaseTitle(live?.phase),
        message: live?.detail ?? "KythOS is downloading the update and preparing it for your next restart. Your current system remains usable.",
        next: hasPercent
          ? `${live.pct}% complete. Keep the Hub open until staging finishes.`
          : "The update is running; progress will appear as soon as the system reports download activity.",
        progress: true,
        phase: recognizedUpdatePhase(live?.phase),
        progressPct: hasPercent ? live.pct : undefined,
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
        phase: stageProgress?.active ? recognizedUpdatePhase(stageProgress.phase) : undefined,
      };
    }
    if (busy === null && updateTracked && !stagedEffective) {
      const live = stageProgress?.active === true ? stageProgress : null;
      return {
        tone: "muted",
        icon: "↓",
        title: live ? updatePhaseTitle(live.phase) : "An update is still running",
        message: live?.detail ?? "A previous update action is still running in the background. Its progress resumes here.",
        next: live?.pct
          ? `${live.pct}% complete. You can wait or choose “Cancel update” below.`
          : "You can wait for it to finish or choose “Cancel update” below to stop it.",
        progress: true,
        phase: recognizedUpdatePhase(live?.phase),
        progressPct: live?.pct ? live.pct : undefined,
      };
    }
    if (actionFailed) {
      const failure = (status ?? "").replace(/^Failed:\s*/, "");
      return {
        tone: "warn",
        icon: "!",
        title: "The update could not be completed",
        message: failure,
        next: friendlyActionNextStep(failure, lastAction),
      };
    }
    if (stagedEffective) {
      return {
        tone: "warn",
        icon: "✓",
        title: "Update ready — restart to finish",
        message: "The update has been downloaded and safely prepared for the next startup.",
        next: "Choose “Restart to apply” when you’re ready. Save open work first.",
        phaseComplete: true,
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
      message: "We’ll look for a newer KythOS version.",
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
          : lastAction === "stage" && actionFailed
            ? { id: "stage", label: "Try again", pending: "Downloading and staging…", action: stage }
            : { id: "check", label: busy === "check" ? "Checking…" : "Check for updates", pending: "Checking for updates…", action: check };

  const channel = snapshot?.channel ?? "Not identified";
  const version = snapshot?.booted?.version ?? snapshot?.booted?.image ?? "Not identified";
  const lastCheck = updateStatus?.detail && !checkFailed ? updateStatus.detail : "The latest check result will appear here.";
  // Update-domain jobs (stage/apply/rollback/switch) are cancellable while
  // running — including a job reattached after a reload, which has no local
  // `busy` anymore.
  const showUpdateCancel = busy === "stage" || busy === "apply" || busy === "rollback" || (busy === null && updateTracked);

  return (
    <section className="updates-overview" aria-label="Updates overview">
      <div className={`updates-hero updates-hero-${overallTone}`}>
        <div>
          <span className="updates-eyebrow">System updates</span>
          <h1>Keep KythOS current</h1>
          <p>One place to check, stage, and finish system updates. App updates now live on the Apps page.</p>
          <div className="updates-meta" aria-label="Current system">
            <span>Channel <strong>{channel}</strong></span>
            <span>Version <strong>{version}</strong></span>
          </div>
        </div>
        <div className={`updates-ready-chip updates-chip-${overallTone}`}><span />{overallLabel}</div>
      </div>

      <div className={`updates-guidance updates-guidance-${guidance.tone}`} aria-busy={busy !== null || backendBusy}>
        <div className="updates-guidance-icon" aria-hidden="true">{guidance.icon}</div>
        <div className="updates-guidance-copy">
          <strong>{guidance.title}</strong>
          <p>{guidance.message}</p>
          <span>{guidance.next}</span>
          {guidance.progress && (guidance.progressPct !== undefined
            ? <div className="updates-guidance-progress updates-guidance-progress-determinate" role="progressbar" aria-valuenow={guidance.progressPct} aria-valuemin={0} aria-valuemax={100} aria-valuetext={`${guidance.phase ? updatePhases.find((phase) => phase.id === guidance.phase)?.label : "Update"} ${guidance.progressPct}% complete`} aria-label="Update download and staging progress"><i style={{ width: `${guidance.progressPct}%` }} /></div>
            : <div className="updates-guidance-progress" role="progressbar" aria-valuetext={guidance.message} aria-label="Update operation in progress"><i /></div>)}
          {(guidance.phase || guidance.phaseComplete) && (
            <ol className={`updates-phase-track${guidance.phaseComplete ? " updates-phase-track-complete" : ""}`} aria-label="System update stages">
              {updatePhases.map((phase, index) => {
                const currentIndex = guidance.phaseComplete ? updatePhases.length : updatePhaseIndex(guidance.phase);
                const complete = guidance.phaseComplete || index < currentIndex;
                const current = !guidance.phaseComplete && index === currentIndex;
                return (
                  <li
                    className={complete ? "updates-phase-complete" : current ? "updates-phase-current" : ""}
                    key={phase.id}
                    aria-current={current ? "step" : undefined}
                  >
                    <span className="updates-phase-marker" aria-hidden="true">{complete ? "✓" : index + 1}</span>
                    <span className="updates-phase-label">{phase.label}</span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
      <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">{guidance.title}</span>

      <div className="updates-status-grid updates-status-grid-single" aria-label="System update status">
        <section className={`updates-status-card updates-status-card-${systemStatusTone}`} aria-label="KythOS system updates">
          <span className="updates-status-label">System</span>
          <strong>{systemStatusLabel}</strong>
          <p>{systemStatusDetail}</p>
        </section>
      </div>

      <div className="updates-actions-card updates-primary-actions">
        <div>
          <span className="updates-eyebrow">Next step</span>
          <h2>{stagedEffective ? "Finish the staged update" : systemUpdateAvailable ? "Install the available update" : "Update KythOS"}</h2>
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
              onClick={() => void cancelRunning()}
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
          <div><span>Last result</span><strong>{friendlyAvailabilityDetail(lastCheck, "Not checked yet.")}</strong></div>
        </div>
      </details>
    </section>
  );
}
