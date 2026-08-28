import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchAuditCache, type AuditCache } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Play > Performance" — scheduler / memory tunables from audit-cache.
export function PerformanceSection({ section }: { section: HubSection }) {
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let c = false;
    fetchAuditCache().then((a) => {
      if (!c) {
        setAudit(a);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={audit !== null}>
      {audit ? (
        <div style={{ marginTop: 20 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(["sched", "thp", "zswap", "swappiness", "sched_latency", "autogroup", "pipewire_gaming"] as const).map((k) => (
              <span key={k} className="pill pill-dim">{k}: {String(audit[k] ?? "—")}</span>
            ))}
          </div>
          {audit.systemd_analyze && <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>{String(audit.systemd_analyze)}</p>}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
