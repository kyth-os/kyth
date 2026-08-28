import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchAuditCache,
  fetchBootRuntimeChecks,
  fetchIsLiveSession,
  fetchMemoryPressure,
  type AuditCache,
  type BootRuntimeCheck,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// "This PC > Health Report" — perf audit cache (30s TTL) covers 50+
// tunables plus systemd-analyze, alongside the boot-runtime checks the
// Dashboard gauge summarizes and the memory-pressure read Repair shares.
// Full audit text is in kyth_shared.perf_audit.format_audit, reachable via
// the `system-audit` recipe below.
function isOk(v: unknown): boolean {
  const s = String(v ?? "").toLowerCase();
  return s === "ok" || s === "enabled" || s === "active" || s === "optimal";
}

export function DiagnosticsSection({ section }: { section: HubSection }) {
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [checks, setChecks] = useState<BootRuntimeCheck[] | null>(null);
  const [memory, setMemory] = useState<{ status: string; detail: string } | null>(null);
  const [liveSession, setLiveSession] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAuditCache(), fetchBootRuntimeChecks(), fetchMemoryPressure(), fetchIsLiveSession()]).then(
      ([a, c, m, isLive]) => {
        if (!cancelled) {
          setAudit(a);
          setChecks(c);
          setMemory(m);
          setLiveSession(isLive);
          setLoaded(true);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const failed = checks?.filter((c) => !c.passed) ?? [];
  const live = audit !== null || checks !== null || memory !== null;

  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            {checks && (
              <span className={`pill ${failed.length === 0 ? "pill-ok" : "pill-warn"}`}>
                boot checks: {checks.length - failed.length}/{checks.length} passed
              </span>
            )}
            {memory && (
              <span className={`pill ${memory.status === "ok" ? "pill-ok" : "pill-warn"}`}>memory: {memory.status}</span>
            )}
            {liveSession && <span className="pill pill-warn">live ISO session — changes are not persistent</span>}
          </div>

          {failed.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Needs attention
              </p>
              {failed.map((check) => (
                <p key={check.name} className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>
                  <strong>{check.name}</strong> — {check.detail}
                </p>
              ))}
            </div>
          )}

          {audit && (
            <>
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
                <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>
                  {Object.keys(audit).length - 1} checks total — full report below.
                </p>
              )}
            </>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <RecipeButton recipe="system-audit" label="Full system audit" busy={busy} run={run} />
          <RecipeButton recipe="gaming-audit" label="Gaming stack audit" busy={busy} run={run} />
          <RecipeButton recipe="update-health" label="Update health" busy={busy} run={run} />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
