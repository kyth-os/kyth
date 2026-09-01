import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchMigrationReadiness, fetchNtfsDevices, fetchNtfsDrives, openMoveFilesApp, runPrivilegedAction, type MigrationReadiness, type NtfsDevice, type NtfsDrive } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

/** Flattens lsblk's nested blockdevices to the rows this section shows.
 * The live read returns whole disks with partitions underneath; only the
 * NTFS partitions are interesting for migrating files off Windows. */
function ntfsPartitions(devices: NtfsDevice[]): NtfsDrive[] {
  const out: NtfsDrive[] = [];
  const walk = (node: NtfsDevice) => {
    if (node.fstype === "ntfs" || node.fstype === "ntfs3" || node.fstype === "BitLocker") {
      out.push({
        dev: `/dev/${node.name ?? "?"}`,
        name: node.name ?? "",
        size: "",
        label: node.label ?? "",
        mount: node.mountpoint ?? "",
        is_bitlocker: node.fstype === "BitLocker",
      });
    }
    (node.children ?? []).forEach(walk);
  };
  devices.forEach(walk);
  return out;
}

// "Move In > Move Files" — other-system NTFS/BitLocker partitions. Mount
// reads the cached "ntfs-drives" probe section; Rescan runs lsblk live,
// which is what you want after plugging the old machine's disk in.
export function MoveFilesSection({ section }: { section: HubSection }) {
  const [drives, setDrives] = useState<NtfsDrive[] | null>(null);
  const [readiness, setReadiness] = useState<MigrationReadiness | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [unlockDevice, setUnlockDevice] = useState<NtfsDrive | null>(null);
  const [unlockKey, setUnlockKey] = useState("");
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchNtfsDrives(), fetchMigrationReadiness()]).then(([d, migration]) => {
      if (!cancelled) {
        setDrives(d);
        setReadiness(migration);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={drives !== null}>
      {drives ? (
        drives.length > 0 ? (
          <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 8 }}>
            {drives.map((drv) => (
              <div
                key={drv.dev}
                style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}
              >
                <span className={`pill ${drv.is_bitlocker ? "pill-warn" : "pill-dim"}`}>
                  {drv.is_bitlocker ? "BitLocker" : "NTFS"}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{drv.dev}</span>
                <span className="card-copy" style={{ fontSize: 12 }}>{drv.label || drv.size || "unlabelled"}</span>
                {drv.mount && <span className="card-copy" style={{ fontSize: 12 }}>mounted at {drv.mount}</span>}
                {drv.is_bitlocker && <ActionButton label="Unlock…" disabled={busy !== null} onClick={() => { setUnlockDevice(drv); setUnlockKey(""); }} />}
              </div>
            ))}
          </div>
        ) : (
          <p className="card-copy" style={{ marginTop: 20, fontSize: 13 }}>No NTFS drives detected — nothing to migrate from.</p>
        )
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
      {readiness && <div style={{ marginTop: 16, padding: 12, border: "1px solid var(--hairline)", borderRadius: 10 }}>
        <p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>Migration readiness — {readiness.parity === "ok" ? "ready" : "needs attention"}</p>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>Drives: {readiness.drives} · Files: {readiness.files} · Bookmarks: {readiness.bookmarks} · Cloud: {readiness.onedrive} · {readiness.pwa}</p>
      </div>}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
          Migration helpers inspect the Windows volume first. The migration workspace gives you a preview before anything is copied or changed.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton label={busy === "open-migration" ? "Opening…" : "Open full migration"} disabled={busy !== null} onClick={() => run("open-migration", "Opening the Windows migration workflow…", openMoveFilesApp)} />
          <ActionButton
            label={busy === "rescan" ? "Rescanning…" : "Rescan drives"}
            disabled={busy !== null}
            onClick={() =>
              run("rescan", "Running lsblk…", async () => {
                const devices = await fetchNtfsDevices();
                if (!devices) return "Not available outside the Hub shell.";
                const found = ntfsPartitions(devices);
                setDrives(found);
                return found.length > 0 ? `${found.length} Windows partition(s) found.` : "No NTFS partitions found.";
              })
            }
          />
          <ActionButton label={busy === "windows-verify" ? "Checking…" : "Check the Windows install"} disabled={busy !== null} onClick={() => run("windows-verify", "Checking Windows install…", () => runPrivilegedAction("windows_verify"))} />
          <RecipeButton recipe="fix-dualboot-clock" label="Fix dual-boot clock" busy={busy} run={run} />
          <RecipeButton recipe="setup-boot-windows-steam" label="Prepare Windows + Steam" busy={busy} run={run} />
          <RecipeButton recipe="reclaim-windows" label="Reclaim Windows space" busy={busy} run={run} />
          <RecipeButton recipe="install-ludusavi" label="Install save migration" busy={busy} run={run} />
          <RecipeButton recipe="install-ms-fonts" label="Install Microsoft fonts" busy={busy} run={run} />
        </div>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 12 }}>
          The full workflow includes verified file-copy previews, bookmarks, save locations, and migration readiness checks.
        </p>
        {unlockDevice && <div style={{ marginTop: 14, padding: 12, border: "1px solid var(--hairline)", borderRadius: 10 }}>
          <p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>Unlock {unlockDevice.dev}</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 5 }}>The key is sent only to the local privileged service and is not logged.</p>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input type="password" value={unlockKey} onChange={(event) => setUnlockKey(event.target.value)} placeholder="BitLocker password or recovery key" style={{ flex: 1, padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)" }} />
            <ActionButton label="Unlock" disabled={busy !== null || unlockKey.length < 8} onClick={() => run("unlock", "Unlocking BitLocker volume…", async () => { try { return await runPrivilegedAction("bitlocker_unlock", { device: unlockDevice.dev, key: unlockKey }); } finally { setUnlockDevice(null); setUnlockKey(""); } })} />
            <ActionButton label="Cancel" disabled={busy !== null} onClick={() => setUnlockDevice(null)} />
          </div>
        </div>}
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
