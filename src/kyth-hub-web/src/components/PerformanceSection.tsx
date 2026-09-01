import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { applyPipewireQuantum, fetchAudioPresets, fetchAuditCache, fetchTelemetryRecent, type AuditCache, type TelemetrySession } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// "Play > Performance" — scheduler / memory tunables from audit-cache,
// plus the two things you can actually change from here: the system
// performance profile (via its ujust recipe) and the PipeWire quantum,
// which is the audio-latency knob that matters for gaming.
export function PerformanceSection({ section }: { section: HubSection }) {
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [audioPresets, setAudioPresets] = useState<string[] | null>(null);
  const [sessions, setSessions] = useState<TelemetrySession[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [pendingPreset, setPendingPreset] = useState<string | null>(null);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let c = false;
    Promise.all([fetchAuditCache(), fetchAudioPresets(), fetchTelemetryRecent(8)]).then(([a, p, recent]) => {
      if (!c) {
        setAudit(a);
        setAudioPresets(p);
        setSessions(recent);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={audit !== null || audioPresets !== null || sessions !== null}>
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
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Recent gaming sessions</p>
        {sessions && sessions.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 10 }}>
            {sessions.map((session, index) => (
              <div key={`${session.started_at ?? "session"}-${index}`} style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap", padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
                <strong style={{ minWidth: 150 }}>{session.game_name || "Unnamed game"}</strong>
                <span className="card-copy" style={{ fontSize: 12 }}>{session.avg_fps != null ? `${Math.round(session.avg_fps)} FPS avg` : "FPS unavailable"}</span>
                {session.p1_low_fps != null && <span className="card-copy" style={{ fontSize: 12 }}>1% low {Math.round(session.p1_low_fps)}</span>}
                {session.stutter_count > 0 && <span className="pill pill-dim">{session.stutter_count} stutters</span>}
                {session.scheduler && <span className="pill pill-dim">{session.scheduler}</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>{sessions ? "No telemetry sessions recorded yet — play a game and check back." : "Telemetry is unavailable outside the installed Tauri Hub."}</p>
        )}
      </div>

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
                  label={pendingPreset === preset ? "Preview ready — confirm below" : busy === `pw-${preset}` ? `Previewing ${preset}…` : preset}
                  disabled={busy !== null || pendingPreset !== null}
                  onClick={() =>
                    run(`pw-${preset}`, `Applying ${preset}…`, async () => {
                      const res = await applyPipewireQuantum(preset, true);
                      if (!res) return "Not available outside the Hub shell.";
                      if (res.ok) setPendingPreset(preset);
                      return res.detail;
                    })
                  }
                />
              ))}
            </div>
            {pendingPreset && (
              <div style={{ marginTop: 12, padding: 12, border: "1px solid var(--status-warn)", borderRadius: 10 }}>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>Apply {pendingPreset} audio latency?</p>
                <p className="card-copy" style={{ margin: "4px 0 10px", fontSize: 12 }}>
                  This writes the PipeWire user configuration and takes effect after PipeWire reloads. Confirm only if you want to change the current profile.
                </p>
                <div style={{ display: "flex", gap: 8 }}>
                  <ActionButton
                    label={busy === `pw-apply-${pendingPreset}` ? "Applying…" : "Confirm"}
                    disabled={busy !== null}
                    onClick={() => run(`pw-apply-${pendingPreset}`, `Applying ${pendingPreset}…`, async () => {
                      const res = await applyPipewireQuantum(pendingPreset, false);
                      setPendingPreset(null);
                      return res?.detail ?? "Not available outside the Hub shell.";
                    })}
                  />
                  <ActionButton label="Cancel" disabled={busy !== null} onClick={() => setPendingPreset(null)} />
                </div>
              </div>
            )}
          </>
        )}

        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Advanced gaming paths</p>
          {/* These legacy launch strings remain documented for bridge parity;
              the rendered controls below are the native replacement. */}
          {/* ujust gamescope -- %command% · ujust game-hdr -- %command% · ujust low-latency -- %command% · ujust scx status */}
          <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>
            These native actions expose the same Gamescope, sched-ext, and low-latency paths without requiring Steam launch flags or a terminal.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
            <RecipeButton recipe="hdr-per-game" label="Build HDR per-game config" busy={busy} run={run} />
            <RecipeButton recipe="enable-bpftune" label="Enable experimental bpftune" busy={busy} run={run} />
            <RecipeButton recipe="disable-bpftune" label="Remove bpftune" busy={busy} run={run} />
          </div>
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
