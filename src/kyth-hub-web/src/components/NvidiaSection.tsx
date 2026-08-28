import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNvidiaDetected } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// Real "This PC > NVIDIA Drivers" content — the "nvidia-detect" probe
// section, already cached for the GPU stat tile; no new backend needed.
export function NvidiaSection({ section }: { section: HubSection }) {
  const [detected, setDetected] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchNvidiaDetected().then((d) => {
      if (!cancelled) {
        setDetected(d);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <LiveSectionCard section={section} live={detected !== null}>
      {detected !== null ? (
        <div style={{ marginTop: 20 }}>
          <span className={`pill ${detected ? "pill-ok" : "pill-dim"}`}>
            {detected ? "NVIDIA GPU detected" : "No NVIDIA GPU detected"}
          </span>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
