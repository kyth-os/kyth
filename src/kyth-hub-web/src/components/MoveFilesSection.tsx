import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNtfsDrives, type NtfsDrive } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Move In > Move Files" — other-system NTFS/BitLocker partitions from
// ntfs-drives probe. Previously preview-only; now live via disk cache.
export function MoveFilesSection({ section }: { section: HubSection }) {
  const [drives, setDrives] = useState<NtfsDrive[] | null>(null);
  const [loaded, setLoaded] = useState(false);
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
              <div key={drv.dev} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
                <span className={`pill ${drv.is_bitlocker ? "pill-warn" : "pill-dim"}`}>{drv.is_bitlocker ? "BitLocker" : "NTFS"}</span>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{drv.dev}</span>
                <span className="card-copy" style={{ fontSize: 12 }}>{drv.label || drv.size}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="card-copy" style={{ marginTop: 20, fontSize: 13 }}>No NTFS drives detected — nothing to migrate from.</p>
        )
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
