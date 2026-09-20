import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchControllers, fetchControllersLive, type ControllerInfo, type ControllersLive } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

// Real "Play > Controllers" content — kyth_shared.system.controllers'
// detect_controllers(). Mount reads the disk-backed "controllers-detect"
// probe section (cheap); the Rescan button runs the live lsusb+lsmod
// detect, which is what you want right after plugging a pad in. The live
// result wins once it exists.
// Browser Gamepad API input tester: polls navigator.getGamepads() at 4Hz
// while enabled and renders live axes/buttons. Client-side only — no
// backend traffic, works even when the Hub shell is unreachable.
function GamepadTester() {
  const [testing, setTesting] = useState(false);
  const [pads, setPads] = useState<Array<{ id: string; axes: number[]; buttons: boolean[] }>>([]);
  useEffect(() => {
    if (!testing) return;
    const timer = window.setInterval(() => {
      const found: Array<{ id: string; axes: number[]; buttons: boolean[] }> = [];
      for (const pad of navigator.getGamepads()) {
        if (pad && pad.connected) found.push({ id: pad.id, axes: [...pad.axes], buttons: pad.buttons.map((b) => b.pressed) });
      }
      setPads(found);
    }, 250);
    return () => window.clearInterval(timer);
  }, [testing]);
  if (!("getGamepads" in navigator)) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <ActionButton label={testing ? "Stop input test" : "Test controller inputs"} onClick={() => setTesting((on) => !on)} />
      {testing && (
        pads.length === 0
          ? <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>No gamepad visible to the browser yet — press any button on the controller to wake it, then check the browser granted gamepad access.</p>
          : pads.map((pad) => (
            <div key={pad.id} style={{ marginTop: 8, padding: "8px 10px", border: "1px solid var(--hairline)", borderRadius: 8 }}>
              <p style={{ margin: 0, fontSize: 12, fontWeight: 600 }}>{pad.id}</p>
              <p className="card-copy" style={{ fontSize: 12, margin: "4px 0 0" }}>Axes: {pad.axes.map((a) => a.toFixed(2)).join(" · ")}</p>
              <p className="card-copy" style={{ fontSize: 12, margin: "4px 0 0" }}>Pressed: {pad.buttons.map((down, i) => (down ? i : null)).filter((i) => i !== null).join(", ") || "none — press buttons to see them light up"}</p>
            </div>
          ))
      )}
    </div>
  );
}

export function ControllersSection({ section }: { section: HubSection }) {
  const [info, setInfo] = useState<ControllerInfo | null>(null);
  const [live, setLive] = useState<ControllersLive | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction("hub-action");

  useEffect(() => {
    let cancelled = false;
    fetchControllers().then((c) => {
      if (!cancelled) {
        setInfo(c);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Normalize both shapes to the one the list below renders.
  const pads = live
    ? live.usb_controllers.map(([name, kind]) => ({ name, kind }))
    : (info?.usbControllers ?? null);
  const drivers = live
    ? { xone: live.xone_loaded, xpadneo: live.xpadneo_loaded, hidPlaystation: live.hid_ps_loaded }
    : (info?.driverLoaded ?? null);
  const inputNodes = live ? live.input_nodes.length : (info?.inputNodeCount ?? null);

  return (
    <LiveSectionCard section={section} live={pads !== null}>
      {pads ? (
        <div style={{ marginTop: 20 }}>
          {pads.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {pads.map((c, i) => (
                <div
                  key={`${c.kind}-${i}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "10px 4px",
                    borderBottom: "1px solid var(--hairline)",
                  }}
                >
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--status-ok)", flexShrink: 0 }} />
                  <p style={{ margin: 0, fontSize: 13, fontWeight: 600, flex: 1 }}>{c.name}</p>
                  <span className="pill pill-dim" style={{ flexShrink: 0 }}>
                    {c.kind}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="card-copy" style={{ fontSize: 13 }}>
              No game controllers detected right now — plug one in and rescan.
            </p>
          )}

          {drivers && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 14 }}>
              {(
                [
                  ["xone", drivers.xone],
                  ["xpadneo", drivers.xpadneo],
                  ["hid-playstation", drivers.hidPlaystation],
                ] as const
              ).map(([name, on]) => (
                <span key={name} className={`pill ${on ? "pill-ok" : "pill-dim"}`}>
                  {name}: {on ? "loaded" : "not loaded"}
                </span>
              ))}
              {inputNodes != null && <span className="pill pill-dim">{inputNodes} input nodes</span>}
              {live?.xone_dongle && <span className="pill pill-ok">Xbox wireless dongle</span>}
              {live?.dualsense_found && <span className="pill pill-ok">DualSense</span>}
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <ActionButton
          label={busy === "rescan" ? "Rescanning…" : "Rescan controllers"}
          disabled={busy !== null}
          onClick={() =>
            run("rescan", "Rescanning…", async () => {
              const fresh = await fetchControllersLive();
              if (!fresh) return "Not available outside the Hub shell.";
              setLive(fresh);
              return `${fresh.usb_controllers.length} controller(s), ${fresh.input_nodes.length} input node(s).`;
            })
          }
        />
        <ActionStatus status={status} />
        <GamepadTester />
      </div>
    </LiveSectionCard>
  );
}
