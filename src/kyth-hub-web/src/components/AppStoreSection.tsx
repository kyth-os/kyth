import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchAppStoreSnapshot, type AppStoreSnapshot } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// Real "Apps > App Store" content — flatpak-apps / flatpak-updates probe
// sections (see services/liveData.ts).
export function AppStoreSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<AppStoreSnapshot | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAppStoreSnapshot().then((s) => {
      if (!cancelled) {
        setSnapshot(s);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <LiveSectionCard section={section} live={snapshot !== null}>
      {snapshot ? (
        <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
              Flatpaks installed
            </p>
            <p style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 800 }}>
              {snapshot.installedCount ?? "—"}
            </p>
          </div>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
              Updates available
            </p>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
              <span style={{ fontSize: 22, fontWeight: 800 }}>{snapshot.updatesAvailable ?? "—"}</span>
              {snapshot.updatesAvailable != null && (
                <span className={`pill ${snapshot.updatesAvailable === 0 ? "pill-ok" : "pill-warn"}`}>
                  {snapshot.updatesAvailable === 0 ? "up to date" : "pending"}
                </span>
              )}
            </div>
          </div>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
