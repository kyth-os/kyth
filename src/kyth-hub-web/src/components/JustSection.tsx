import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchAuditCache, type AuditCache } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "This PC > Recipes (Just)" — no dedicated probe yet; surface the audit
// master + a hint that Just recipes are available via the welcome CLI.
export function JustSection({ section }: { section: HubSection }) {
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
          <p className="card-copy" style={{ fontSize: 12 }}>Master profile: <strong>{String(audit.master ?? "unknown")}</strong> — run `just --list` for recipes.</p>
          <p className="card-copy" style={{ fontSize: 11, marginTop: 6, color: "var(--text-dim)" }}>Audit provides {Object.keys(audit).length} tunable checks that Just recipes can apply.</p>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
