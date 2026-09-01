import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchBootcSnapshot,
  fetchBtrfsHealth,
  fetchDeploymentHistory,
  fetchMemoryPressure,
  fetchRecoveryStatus,
  fetchSnapshotCount,
  fetchSnapshotTimeline,
  fetchInstallStatus,
  installFlatpak,
  openBackupApp,
  invokeBootcRollback,
  relativeTime,
  type BootcSnapshot,
  type DeploymentInfo,
  type RecoveryStatus,
  type SnapshotRow,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

function ago(timestamp: string | null | undefined): string | null {
  if (!timestamp) return null;
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) return null;
  return relativeTime(ms / 1000);
}

// Real "This PC > Repair" content — everything that answers "can I get
// back to a working system": the recovery banner (staged/rollback/
// quarantined image), the bootc deployment timeline, snapshot count, and
// the two filesystem/memory health reads. All of these are local reads, so
// they all run on mount; the recovery actions are separate buttons.
//
// `bootc rollback` runs through the same bridge command Updates uses; the
// argv is also shown, because a system that needs repairing is exactly the
// one where you may end up running it from a TTY instead.
export function RepairSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<BootcSnapshot | null>(null);
  const [recovery, setRecovery] = useState<RecoveryStatus | null>(null);
  const [history, setHistory] = useState<DeploymentInfo[] | null>(null);
  const [timeline, setTimeline] = useState<SnapshotRow[] | null>(null);
  const [snapshots, setSnapshots] = useState<number | null>(null);
  const [btrfs, setBtrfs] = useState<{ status: string; detail: string } | null>(null);
  const [memory, setMemory] = useState<{ status: string; detail: string } | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  async function installBackup(): Promise<string> {
    const job = await installFlatpak("org.gnome.World.PikaBackup");
    for (let i = 0; i < 120; i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 500));
      const state = await fetchInstallStatus(job);
      if (!state || state.state === "running") continue;
      if (state.state === "complete") return "Pika Backup installed.";
      throw new Error(state.detail);
    }
    throw new Error("Pika Backup is still installing; check Apps for progress.");
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchBootcSnapshot(),
      fetchRecoveryStatus(),
      fetchDeploymentHistory(),
      fetchSnapshotCount(),
      fetchSnapshotTimeline(20),
      fetchBtrfsHealth(),
      fetchMemoryPressure(),
    ]).then(([snap, rec, hist, count, rows, fs, mem]) => {
      if (!cancelled) {
        setSnapshot(snap);
        setRecovery(rec);
        setHistory(hist);
        setSnapshots(count);
        setTimeline(rows);
        setBtrfs(fs);
        setMemory(mem);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasRollback = recovery?.has_rollback ?? snapshot?.rollback != null;
  const live = snapshot !== null || recovery !== null || btrfs !== null;

  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          {recovery?.banner && (
            <p
              className="card-copy"
              style={{ fontSize: 13, padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: 10 }}
            >
              {recovery.banner}
            </p>
          )}

          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
            <span className={`pill ${hasRollback ? "pill-ok" : "pill-warn"}`}>
              rollback: {hasRollback ? "available" : "none"}
            </span>
            {recovery && (
              <span className={`pill ${recovery.has_staged ? "pill-warn" : "pill-dim"}`}>
                staged: {recovery.has_staged ? "yes" : "no"}
              </span>
            )}
            {recovery?.quarantined_digest && <span className="pill pill-warn">image quarantined</span>}
            {snapshots != null && <span className="pill pill-dim">{snapshots} snapshot(s)</span>}
            {btrfs && (
              <span className={`pill ${btrfs.status === "ok" ? "pill-ok" : "pill-warn"}`}>btrfs: {btrfs.status}</span>
            )}
            {memory && (
              <span className={`pill ${memory.status === "ok" ? "pill-ok" : "pill-warn"}`}>memory: {memory.status}</span>
            )}
          </div>

          {recovery?.quarantine_detail && (
            <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>{recovery.quarantine_detail}</p>
          )}
          {btrfs?.detail && <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>{btrfs.detail}</p>}
          {memory?.detail && <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>{memory.detail}</p>}

          {history && history.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Deployments
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 8 }}>
                {history.map((entry) => (
                  <div
                    key={entry.section}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "9px 4px",
                      borderBottom: "1px solid var(--hairline)",
                    }}
                  >
                    <span className={`pill ${entry.available ? "pill-ok" : "pill-dim"}`} style={{ flexShrink: 0 }}>
                      {entry.label}
                    </span>
                    <span style={{ fontSize: 13, flex: 1 }}>{entry.status_text}</span>
                    <span className="card-copy" style={{ fontSize: 11.5, flexShrink: 0 }}>
                      {ago(entry.timestamp) ?? entry.short_digest ?? ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {timeline && timeline.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Snapshots &amp; deployments
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8, marginTop: 8 }}>
                {timeline.map((entry) => (
                  <div
                    key={`${entry.type}-${entry.id}`}
                    style={{ padding: "11px 12px", border: "1px solid var(--hairline)", borderRadius: 10, background: "var(--surface-raised)" }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                      <span className={`pill ${entry.type === "snapshot" ? "pill-dim" : "pill-ok"}`}>{entry.type}</span>
                      <span className="card-copy" style={{ fontSize: 11 }}>{ago(entry.timestamp) ?? entry.id}</span>
                    </div>
                    <p style={{ margin: "9px 0 0", fontSize: 12.5, lineHeight: 1.35 }}>{entry.description || "No description"}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton
            label={busy === "rollback" ? "Rolling back…" : "Roll back to previous"}
            disabled={busy !== null || !hasRollback}
            onClick={() => run("rollback", "Rolling back…", invokeBootcRollback)}
          />
          <RecipeButton recipe="update-health" label="Update health report" busy={busy} run={run} />
          <RecipeButton recipe="resume-check" label="Check suspend/resume" busy={busy} run={run} />
          <RecipeButton recipe="device-info" label="Collect device info" busy={busy} run={run} />
          <RecipeButton recipe="startup-apps" label="Review startup apps" busy={busy} run={run} />
          <RecipeButton recipe="firmware-update" label="Check firmware updates" busy={busy} run={run} />
          <RecipeButton recipe="windows-verify" label="Verify Windows migration" busy={busy} run={run} />
          <ActionButton
            label={busy === "recheck" ? "Re-reading…" : "Re-check"}
            disabled={busy !== null}
            onClick={() =>
              run("recheck", "Re-reading recovery state…", async () => {
                const [rec, fs, mem] = await Promise.all([fetchRecoveryStatus(), fetchBtrfsHealth(), fetchMemoryPressure()]);
                if (!rec && !fs && !mem) return "Not available outside the Hub shell.";
                if (rec) setRecovery(rec);
                if (fs) setBtrfs(fs);
                if (mem) setMemory(mem);
                return rec?.banner || "Recovery state re-read.";
              })
            }
          />
        </div>
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>File History backup</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>Pika Backup keeps versioned copies of your home folder on a USB drive or network location. Kyth does not choose or delete backup data for you.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            <ActionButton label={busy === "install-backup" ? "Installing…" : "Install Pika Backup"} disabled={busy !== null} onClick={() => run("install-backup", "Installing Pika Backup…", installBackup)} />
            <ActionButton label={busy === "open-backup" ? "Opening…" : "Open Pika Backup"} disabled={busy !== null} onClick={() => run("open-backup", "Opening Pika Backup…", openBackupApp)} />
          </div>
        </div>
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Quick fixes</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>Run bounded, reversible maintenance actions without opening a terminal. Guardian remains the automatic path for symptom-based repair.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            <RecipeButton recipe="health-check" label="Run system health check" busy={busy} run={run} />
            <RecipeButton recipe="firmware-update" label="Refresh firmware metadata" busy={busy} run={run} />
            <RecipeButton recipe="gaming-stack-status" label="Check gaming stack" busy={busy} run={run} />
          </div>
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
