import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchMokStatus, fetchHardwareSnapshot, type MokStatus } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Play > Compatibility" — now live via Rust mok_verify (mokutil) + hardware-summary
// for ProtonDB / anti-cheat context. Replaces probe-cache secureboot-state with
// live MOK enrollment detail.
export function CompatibilitySection({ section }: { section: HubSection }) {
  const [mok, setMok] = useState<MokStatus | null>(null);
  const [hwCaps, setHwCaps] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let c = false;
    Promise.all([fetchMokStatus(), fetchHardwareSnapshot()]).then(([m, h]) => {
      if (!c) {
        setMok(m);
        setHwCaps(h?.capabilities ?? null);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  const live = mok !== null || hwCaps !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          {mok && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span className={`pill ${mok.sb_state === "enabled" ? "pill-ok" : "pill-dim"}`}>Secure Boot: {mok.sb_state}</span>
              <span className={`pill ${mok.enrolled === "enrolled" ? "pill-ok" : "pill-dim"}`}>MOK: {mok.enrolled}</span>
            </div>
          )}
          {hwCaps && hwCaps.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              {hwCaps.slice(0, 6).map((cap) => (
                <span key={cap} className="pill pill-dim">{cap}</span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
