import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { applyPipewireQuantum, fetchAudioPresets, fetchAuditCache, type AuditCache } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// "Play > Performance" — scheduler / memory tunables from audit-cache,
// plus the two things you can actually change from here: the system
// performance profile (via its ujust recipe) and the PipeWire quantum,
// which is the audio-latency knob that matters for gaming.
export function PerformanceSection({ section }: { section: HubSection }) {
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [audioPresets, setAudioPresets] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let c = false;
    Promise.all([fetchAuditCache(), fetchAudioPresets()]).then(([a, p]) => {
      if (!c) {
        setAudit(a);
        setAudioPresets(p);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={audit !== null || audioPresets !== null}>
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

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
          Power profile
        </p>
        <p className="card-copy" style={{ fontSize: 12, margin: "6px 0 0" }}>
          The gaming profile sets EPP to performance and also halves animation speed and turns off blur; Balanced puts
          both back.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
          <RecipeButton recipe="gaming-mode" label="Performance (gaming profile)" busy={busy} run={run} />
          <RecipeButton recipe="balanced-mode" label="Balanced" busy={busy} run={run} />
          <RecipeButton recipe="system-audit" label="Run full audit" busy={busy} run={run} />
        </div>

        {audioPresets && audioPresets.length > 0 && (
          <>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, marginTop: 18 }}>
              Audio latency (PipeWire quantum)
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
              {audioPresets.map((preset) => (
                <ActionButton
                  key={preset}
                  label={busy === `pw-${preset}` ? `Applying ${preset}…` : preset}
                  disabled={busy !== null}
                  onClick={() =>
                    run(`pw-${preset}`, `Applying ${preset}…`, async () => {
                      const res = await applyPipewireQuantum(preset, false);
                      if (!res) return "Not available outside the Hub shell.";
                      return res.detail;
                    })
                  }
                />
              ))}
            </div>
          </>
        )}
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
