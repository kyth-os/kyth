import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchHardwareSnapshot, type HardwareSnapshot } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// Real "This PC > Hardware" content — GPU name (one lspci call, see
// kyth_shared::system::gpu::lspci_gpu_lines) plus the
// has_nvidia/is_hybrid/capabilities summary from the "hardware-summary"
// probe section (see services/liveData.ts).
export function HardwareSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<HardwareSnapshot | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchHardwareSnapshot().then((s) => {
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
        <div style={{ marginTop: 24 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            Graphics
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.gpuName ?? "Unknown"}</p>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            {snapshot.hasNvidia && <span className="pill pill-dim">NVIDIA</span>}
            {snapshot.isHybrid && <span className="pill pill-dim">Hybrid graphics</span>}
          </div>
          {snapshot.capabilities.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Capabilities
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {snapshot.capabilities.map((cap) => (
                  <span key={cap} className="pill pill-dim">
                    {cap}
                  </span>
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
