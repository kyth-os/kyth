import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchAuditCache, type AuditCache } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "This PC > Health Report" — perf audit cache (30s TTL) covers 50+
// tunables plus systemd-analyze. Show the headline numbers; full audit is
// in kyth_shared.perf_audit.format_audit.
function isOk(v: unknown): boolean {
  const s = String(v ?? "").toLowerCase();
  return s === "ok" || s === "enabled" || s === "active" || s === "optimal";
}
export function DiagnosticsSection({ section }: { section: HubSection }) {
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetchAuditCache().then((a) => {
      if (!cancelled) {
        setAudit(a);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={audit !== null}>
      {audit ? (
        <div style={{ marginTop: 20 }}>
          {audit.systemd_analyze && (
            <p className="card-copy" style={{ fontSize: 12, marginBottom: 12 }}>{String(audit.systemd_analyze)}</p>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {Object.entries(audit)
              .filter(([k]) => k !== "ts" && k !== "systemd_analyze" && k !== "telemetry")
              .slice(0, 12)
              .map(([k, v]) => (
                <span key={k} className={`pill ${isOk(v) ? "pill-ok" : "pill-dim"}`} title={`${k}: ${String(v)}`}>
                  {k}: {String(v).slice(0, 24)}
                </span>
              ))}
          </div>
          {Object.keys(audit).length > 13 && (
            <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>{Object.keys(audit).length - 1} checks total — full report via `kyth perf audit`.</p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
