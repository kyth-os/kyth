import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchAuditCache, fetchGamingLibrary, type AuditCache, type LauncherEntry } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Play > Gaming" — audit master profile + live launcher library scan.
// Previously only audit pills; now also shows which launchers are installed
// and library counts, matching page_gaming_library.py's Steam/Heroic scan.
export function GamingSection({ section }: { section: HubSection }) {
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [launchers, setLaunchers] = useState<LauncherEntry[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let c = false;
    Promise.all([fetchAuditCache(), fetchGamingLibrary()]).then(([a, l]) => {
      if (!c) {
        setAudit(a);
        setLaunchers(l);
        setLoaded(true);
      }
    });
    return () => { c = true; };
  }, []);
  const live = audit !== null || launchers !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {audit ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Master profile</p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{String(audit.master ?? "unknown")}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
            {(["loader", "oom_gaming", "shader_tmpfs", "gaming_cfs", "ananicy", "kwin"] as const).map((k) => (
              <span key={k} className="pill pill-dim">{k}: {String(audit[k] ?? "\u2014")}</span>
            ))}
          </div>
          {launchers && launchers.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Launchers</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {launchers.map((l) => (
                  <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
                    <span className={`pill ${l.installed ? "pill-ok" : "pill-dim"}`}>{l.installed ? "installed" : "not installed"}</span>
                    <span style={{ fontWeight: 600 }}>{l.label}</span>
                    <span className="card-copy" style={{ fontSize: 12 }}>{l.library_count != null ? `${l.library_count} games` : l.path}</span>
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
