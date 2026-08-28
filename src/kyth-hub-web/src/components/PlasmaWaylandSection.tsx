import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchDisplayDetect, type DisplayDetect } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "This PC > Desktop & displays" — capabilities/profiles from
// display-detect (hardware_policy.evaluate_system), now disk-backed after
// the DISK_TTL fix. Same data HardwareSection shows partially, full view here.
export function PlasmaWaylandSection({ section }: { section: HubSection }) {
  const [data, setData] = useState<DisplayDetect | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetchDisplayDetect().then((d) => {
      if (!cancelled) {
        setData(d);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={data !== null}>
      {data ? (
        <div style={{ marginTop: 20 }}>
          {data.capabilities.length > 0 && (
            <div>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Capabilities</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {data.capabilities.map((c) => (
                  <span key={c} className="pill pill-dim">{c}</span>
                ))}
              </div>
            </div>
          )}
          {data.profiles.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Profiles</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {data.profiles.map((p) => (
                  <span key={p} className="pill pill-dim">{p}</span>
                ))}
              </div>
            </div>
          )}
          {data.capabilities.length === 0 && data.profiles.length === 0 && (
            <p className="card-copy" style={{ marginTop: 10, fontSize: 13 }}>No display capabilities reported.</p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
