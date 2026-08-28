import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  applyPlasmaPreset,
  fetchDesktopStackChecks,
  fetchDisplayDetect,
  fetchPlasmaPresets,
  type DisplayDetect,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// "This PC > Desktop & displays" — capabilities/profiles from
// display-detect (hardware_policy.evaluate_system), the HDR/VRR presets
// plasma_hdr.rs knows how to apply, and a live check of which desktop
// units are actually running.
export function PlasmaWaylandSection({ section }: { section: HubSection }) {
  const [data, setData] = useState<DisplayDetect | null>(null);
  const [presets, setPresets] = useState<string[] | null>(null);
  const [stack, setStack] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchDisplayDetect(), fetchPlasmaPresets(), fetchDesktopStackChecks()]).then(([d, p, s]) => {
      if (!cancelled) {
        setData(d);
        setPresets(p);
        setStack(s);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const live = data !== null || presets !== null || stack !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          {data && data.capabilities.length > 0 && (
            <div>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Capabilities</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {data.capabilities.map((c) => (
                  <span key={c} className="pill pill-dim">{c}</span>
                ))}
              </div>
            </div>
          )}
          {data && data.profiles.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Profiles</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {data.profiles.map((p) => (
                  <span key={p} className="pill pill-dim">{p}</span>
                ))}
              </div>
            </div>
          )}
          {stack && (
            <div style={{ marginTop: 14 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Desktop session
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {stack.length > 0 ? (
                  stack.map((check) => (
                    <span key={check} className="pill pill-ok">{check}</span>
                  ))
                ) : (
                  <span className="pill pill-warn">no desktop units reported active</span>
                )}
              </div>
            </div>
          )}
          {data && data.capabilities.length === 0 && data.profiles.length === 0 && (
            <p className="card-copy" style={{ marginTop: 10, fontSize: 13 }}>No display capabilities reported.</p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      {presets && presets.length > 0 && (
        <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            HDR / VRR preset
          </p>
          <p className="card-copy" style={{ fontSize: 12, margin: "6px 0 12px" }}>
            Applies to the current Wayland session; some changes need the session restarted. A preset the display
            cannot do (HDR on an SDR panel) can leave a black screen, and there is no way back from inside the Hub —
            recover with <code>ujust list-presets</code> from a TTY, or reboot.
          </p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {presets.map((preset) => (
              <ActionButton
                key={preset}
                label={busy === preset ? `Applying ${preset}…` : preset}
                disabled={busy !== null}
                onClick={() =>
                  run(preset, `Applying ${preset}…`, async () => {
                    const res = await applyPlasmaPreset(preset, false);
                    if (!res) return "Not available outside the Hub shell.";
                    return res.detail;
                  })
                }
              />
            ))}
            <RecipeButton recipe="list-presets" label="List all presets" busy={busy} run={run} />
          </div>
          <ActionStatus status={status} />
        </div>
      )}
    </LiveSectionCard>
  );
}
