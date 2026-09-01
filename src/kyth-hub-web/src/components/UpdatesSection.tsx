import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchBootcSnapshot,
  fetchCollectAvailability,
  fetchPendingUpdatesSummary,
  fetchUpdateHealth,
  fetchUpdateAvailabilityView,
  fetchUpdateStatus,
  fetchUpdaterAvailable,
  invokeBootcRollback,
  invokeBootcUpgrade,
  invokeApplyStaged,
  relativeTime,
  type BootcSnapshot,
  type UpdateAvailabilityView,
  type UpdateStatusLive,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

function shortDigest(digest: string | undefined): string | null {
  if (!digest) return null;
  return digest.replace(/^sha256:/, "").slice(0, 12);
}

function ago(timestamp: string | undefined): string | null {
  if (!timestamp) return null;
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) return null;
  return relativeTime(ms / 1000);
}

// The real "Updates" page content — reads the same bootc-status-data /
// bootc-branch probe sections the retired Qt Hub's Update page read,
// through the Tauri probe_backend bridge (see services/liveData.ts).
//
// Mount reads the persisted status plus bounded update summaries. The native
// bridge runs their blocking probes off the webview thread; "Check for
// updates" is still the explicit registry refresh and its result is handed
// to update_availability_view — the Rust port of the Qt page's "what should
// this card say" logic — rather than being re-derived into card copy here.
export function UpdatesSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<BootcSnapshot | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusLive | null>(null);
  const [pending, setPending] = useState<Record<string, unknown> | null>(null);
  const [updaterAvailable, setUpdaterAvailable] = useState<boolean | null>(null);
  const [health, setHealth] = useState<Awaited<ReturnType<typeof fetchUpdateHealth>>>(null);
  const [view, setView] = useState<UpdateAvailabilityView | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  async function readUpdateState() {
    return await Promise.all([
      fetchBootcSnapshot(),
      fetchUpdateStatus(),
      fetchPendingUpdatesSummary(),
      fetchUpdaterAvailable(),
      fetchUpdateHealth(),
    ]);
  }

  useEffect(() => {
    let cancelled = false;
    readUpdateState().then(([snap, live, summary, updater, healthState]) => {
      if (!cancelled) {
        setSnapshot(snap);
        setUpdateStatus(live);
        setPending(summary);
        setUpdaterAvailable(updater);
        setHealth(healthState);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshUpdateState(): Promise<string> {
    const [snap, live, summary, updater, healthState] = await readUpdateState();
    setSnapshot(snap);
    setUpdateStatus(live);
    setPending(summary);
    setUpdaterAvailable(updater);
    setHealth(healthState);
    return "Update status refreshed.";
  }

  async function checkForUpdates(): Promise<string> {
    const availability = await fetchCollectAvailability(null, false);
    if (!availability) return "Not available outside the Hub shell.";
    const card = await fetchUpdateAvailabilityView({
      staged: availability.staged,
      check_state: availability.state,
      flatpak_count: availability.flatpak_count,
      check_ts: "",
      check_ts_details: availability.detail,
    });
    if (card) setView(card);
    setUpdateStatus((current) => current ? {
      ...current,
      staged: availability.staged,
      check_state: availability.state,
      blocked_reason: availability.blocked_reason || null,
      detail: availability.detail,
    } : current);
    setPending((current) => ({ ...(current ?? {}), flatpak: availability.flatpak_count }));
    return availability.blocked_reason || card?.title || availability.detail;
  }

  async function downloadAndStage(): Promise<string> {
    const detail = await invokeBootcUpgrade();
    await refreshUpdateState();
    return detail;
  }

  async function rollback(): Promise<string> {
    const detail = await invokeBootcRollback();
    await refreshUpdateState();
    return detail;
  }

  async function applyStaged(): Promise<string> {
    const detail = await invokeApplyStaged();
    await refreshUpdateState();
    return detail;
  }

  async function healthReport(): Promise<string> {
    const next = await fetchUpdateHealth();
    setHealth(next);
    return next?.detail ?? "Update health is unavailable.";
  }

  const live = snapshot !== null || updateStatus !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {snapshot?.booted ? (
        <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Channel</p>
            <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.channel ?? "Unknown"}</p>
          </div>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Booted version</p>
            <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.booted.version ?? "Unknown"}</p>
            <p className="card-copy" style={{ fontSize: 11.5, marginTop: 2 }}>
              {ago(snapshot.booted.timestamp) ?? "unknown age"} · {shortDigest(snapshot.booted.imageDigest) ?? "no digest"}
            </p>
          </div>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Rollback available</p>
            {snapshot.rollback ? (
              <>
                <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.rollback.version ?? "Unknown"}</p>
                <p className="card-copy" style={{ fontSize: 11.5, marginTop: 2 }}>
                  {ago(snapshot.rollback.timestamp) ?? "unknown age"}
                </p>
              </>
            ) : (
              <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>None</p>
            )}
          </div>
        </div>
      ) : (
        !live && <SectionFallbackNote loaded={loaded} />
      )}

      {(updateStatus || pending) && (
        <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {updateStatus && (
            <>
              <span className={`pill ${updateStatus.staged ? "pill-warn" : "pill-dim"}`}>
                {updateStatus.staged ? "update staged — restart to apply" : "nothing staged"}
              </span>
              <span className="pill pill-dim">check: {updateStatus.check_state}</span>
            </>
          )}
          {pending &&
            Object.entries(pending).map(([key, value]) => (
              <span key={key} className="pill pill-dim">{key}: {String(value)}</span>
            ))}
          {updaterAvailable === false && <span className="pill pill-warn">background updater unavailable</span>}
        </div>
      )}

      {updateStatus?.detail && (
        <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>{updateStatus.detail}</p>
      )}
      {updateStatus?.blocked_reason && (
        <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>Blocked: {updateStatus.blocked_reason}</p>
      )}

      {health && (
        <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
          <span className={`pill ${health.status === "healthy" ? "pill-dim" : "pill-warn"}`}>health: {health.status}</span>
          <span className="pill pill-dim">quarantined: {health.quarantined}</span>
          {health.failures > 0 && <span className="pill pill-warn">failures: {health.failures}</span>}
        </div>
      )}

      {view && (
        <div style={{ marginTop: 16, padding: "12px 14px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 14 }}>
            {view.icon_text} {view.title}
          </p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>{view.body}</p>
        </div>
      )}

      <div style={{ marginTop: 24, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton
            label={busy === "refresh" ? "Refreshing…" : "Refresh status"}
            disabled={busy !== null}
            onClick={() => run("refresh", "Reading update status…", refreshUpdateState)}
          />
          <ActionButton
            label={busy === "check" ? "Checking…" : "Check for updates"}
            disabled={busy !== null}
            onClick={() => run("check", "Asking the registry…", checkForUpdates)}
          />
          <ActionButton
            label={busy === "upgrade" ? "Downloading…" : "Download and stage"}
            disabled={busy !== null}
            onClick={() => run("upgrade", "Downloading and staging…", downloadAndStage)}
          />
          {updateStatus?.staged && <ActionButton label={busy === "apply-staged" ? "Restarting…" : "Restart to apply"} disabled={busy !== null} onClick={() => run("apply-staged", "Applying staged update…", applyStaged)} />}
          <ActionButton label={busy === "health" ? "Checking health…" : "Update health report"} disabled={busy !== null} onClick={() => run("health", "Reading boot health…", healthReport)} />
          <ActionButton
            label={busy === "rollback" ? "Rolling back…" : "Roll back"}
            // Nothing to roll back to until a previous deployment exists.
            disabled={busy !== null || !(snapshot?.rollback || updateStatus?.rollback)}
            onClick={() => run("rollback", "Rolling back…", rollback)}
          />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
