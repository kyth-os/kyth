import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchSecurebootState, fetchHardwareSnapshot } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Play > Compatibility" — Secure Boot + hardware tier context for
// ProtonDB / anti-cheat checks. No dedicated probe yet; Secure Boot +
// hardware-summary give a useful live signal now.
export function CompatibilitySection({ section }: { section: HubSection }) {
  const [sb, setSb] = useState<string | null>(null);
  const [hwCaps, setHwCaps] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let c = false;
    Promise.all([fetchSecurebootState(), fetchHardwareSnapshot()]).then(([s, h]) => {
      if (!c) {
        setSb(s);
        setHwCaps(h?.capabilities ?? null);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  const live = sb !== null || hwCaps !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          {sb !== null && <span className={`pill ${sb === "enabled" ? "pill-ok" : "pill-dim"}`}>Secure Boot: {sb}</span>}
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
