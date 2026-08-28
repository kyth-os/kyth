import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchAppStoreSnapshot, fetchStarterPacks, type AppStoreSnapshot, type StarterPack } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Apps > App Store" — flatpak counts + starter packs catalog (software_catalogs.py).
export function AppStoreSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<AppStoreSnapshot | null>(null);
  const [packs, setPacks] = useState<StarterPack[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAppStoreSnapshot(), fetchStarterPacks()]).then(([s, p]) => {
      if (!cancelled) { setSnapshot(s); setPacks(p); setLoaded(true); }
    });
    return () => { cancelled = true; };
  }, []);
  return (
    <LiveSectionCard section={section} live={snapshot !== null || packs !== null}>
      {snapshot || packs ? (
        <div style={{ marginTop: 20 }}>
          {snapshot && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
              <div>
                <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Flatpaks installed</p>
                <p style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 800 }}>{snapshot.installedCount ?? "\u2014"}</p>
              </div>
              <div>
                <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Updates available</p>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 22, fontWeight: 800 }}>{snapshot.updatesAvailable ?? "\u2014"}</span>
                  {snapshot.updatesAvailable != null && (
                    <span className={`pill ${snapshot.updatesAvailable === 0 ? "pill-ok" : "pill-warn"}`}>{snapshot.updatesAvailable === 0 ? "up to date" : "pending"}</span>
                  )}
                </div>
              </div>
            </div>
          )}
          {packs && packs.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Starter packs</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                {packs.map((pack) => (
                  <div key={pack.name} style={{ padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
                    <p style={{ fontWeight: 700, fontSize: 13 }}>{pack.name}</p>
                    <p className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>{pack.desc}</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {pack.apps.map((a) => (
                        <span key={a.id} className={`pill ${a.selected ? "pill-ok" : "pill-dim"}`}>{a.label}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
