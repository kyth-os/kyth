import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchAuditCache, type AuditCache } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Play > Gaming" — gaming master profile + gamer-relevant audit facets.
export function GamingSection({ section }: { section: HubSection }) {
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
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Master profile</p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{String(audit.master ?? "unknown")}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
            {(["loader", "oom_gaming", "shader_tmpfs", "gaming_cfs", "ananicy", "kwin"] as const).map((k) => (
              <span key={k} className="pill pill-dim">{k}: {String(audit[k] ?? "—")}</span>
            ))}
          </div>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
