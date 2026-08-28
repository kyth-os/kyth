import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNtfsDevices, fetchNtfsDrives, type NtfsDevice, type NtfsDrive } from "../services/liveData";
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
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let cancelled = false;
    fetchNtfsDrives().then((d) => {
      if (!cancelled) {
        setDrives(d);
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
              </div>
            ))}
          </div>
        ) : (
          <p className="card-copy" style={{ marginTop: 20, fontSize: 13 }}>No NTFS drives detected — nothing to migrate from.</p>
        )
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
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
          <RecipeButton recipe="windows-verify" label="Check the Windows install" busy={busy} run={run} />
          <RecipeButton recipe="fix-dualboot-clock" label="Fix dual-boot clock" busy={busy} run={run} />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
