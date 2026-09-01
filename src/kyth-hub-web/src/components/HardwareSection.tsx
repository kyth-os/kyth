import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchFirmwareUpdatesCount,
  fetchHardwareSnapshot,
  fetchHardwareViewSummary,
  fetchLoadedKernelModules,
  fetchPciByClass,
  type HardwareSnapshot,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// PCI class codes worth naming on this page — the GPU is the one that
// decides which driver stack is in play, the audio and network functions
// are the two that most often need a module check alongside it.
const PCI_CLASSES: ReadonlyArray<readonly [string, string]> = [
  ["0300", "Display"],
  ["0403", "Audio"],
  ["0200", "Ethernet"],
];

// Drivers people actually come to this page about. Filtering rather than
// listing all of lsmod keeps this readable — the full list is `lsmod`.
const NOTABLE_MODULES = [
  "amdgpu", "nvidia", "nvidia_drm", "i915", "xe", "nouveau",
  "xone", "xpadneo", "hid_playstation", "hid_nintendo", "ntsync", "btusb",
];

// Real "This PC > Hardware" content — GPU name (one lspci call) plus the
// has_nvidia/is_hybrid/capabilities summary from the "hardware-summary"
// probe section.
//
// Firmware is behind a button on purpose: check_firmware_updates waits on
// fwupd with a 20s timeout, which is far too long to spend on a tab
// switch. The driver/PCI scan is likewise a handful of process spawns.
export function HardwareSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<HardwareSnapshot | null>(null);
  const [modules, setModules] = useState<string[] | null>(null);
  const [pci, setPci] = useState<Array<[string, string[]]> | null>(null);
  const [firmware, setFirmware] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

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
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Graphics</p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.gpuName ?? "Unknown"}</p>
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            {snapshot.hasNvidia && <span className="pill pill-dim">NVIDIA</span>}
            {snapshot.isHybrid && <span className="pill pill-dim">Hybrid graphics</span>}
            {firmware != null && (
              <span className={`pill ${firmware === 0 ? "pill-ok" : "pill-warn"}`}>
                {firmware === 0 ? "firmware up to date" : `${firmware} firmware update(s)`}
              </span>
            )}
          </div>

          {snapshot.capabilities.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Capabilities
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {snapshot.capabilities.map((cap) => (
                  <span key={cap} className="pill pill-dim">{cap}</span>
                ))}
              </div>
            </div>
          )}

          {pci && (
            <div style={{ marginTop: 18 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Devices</p>
              {pci.map(([label, devices]) => (
                <div key={label} style={{ marginTop: 8 }}>
                  <p style={{ margin: 0, fontSize: 12, fontWeight: 700 }}>{label}</p>
                  {devices.length > 0 ? (
                    devices.map((device) => (
                      <p key={device} className="card-copy" style={{ fontSize: 12, marginTop: 2 }}>{device}</p>
                    ))
                  ) : (
                    <p className="card-copy" style={{ fontSize: 12, marginTop: 2 }}>none</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {modules && (
            <div style={{ marginTop: 18 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Drivers loaded
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {modules.length > 0 ? (
                  modules.map((mod) => (
                    <span key={mod} className="pill pill-ok">{mod}</span>
                  ))
                ) : (
                  <span className="pill pill-dim">none of the drivers this page tracks</span>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton
            label={busy === "scan" ? "Scanning…" : "Scan devices and drivers"}
            disabled={busy !== null}
            onClick={() =>
              run("scan", "Reading lspci and lsmod…", async () => {
                const [summary, loadedModules, ...classes] = await Promise.all([
                  fetchHardwareViewSummary(),
                  fetchLoadedKernelModules(),
                  ...PCI_CLASSES.map(([code]) => fetchPciByClass(code)),
                ]);
                if (!loadedModules && !summary) return "Not available outside the Hub shell.";
                if (summary) {
                  setSnapshot((prev) =>
                    prev
                      ? { ...prev, hasNvidia: summary.has_nvidia, isHybrid: summary.is_hybrid, capabilities: summary.capabilities }
                      : { gpuName: null, hasNvidia: summary.has_nvidia, isHybrid: summary.is_hybrid, capabilities: summary.capabilities },
                  );
                }
                if (loadedModules) {
                  const present = new Set(loadedModules);
                  setModules(NOTABLE_MODULES.filter((mod) => present.has(mod)));
                }
                setPci(PCI_CLASSES.map(([, label], i) => [label, classes[i] ?? []] as [string, string[]]));
                return "Hardware re-scanned.";
              })
            }
          />
          <ActionButton
            label={busy === "firmware" ? "Asking fwupd…" : "Check firmware"}
            disabled={busy !== null}
            onClick={() =>
              run("firmware", "Asking fwupd… (this can take up to 20 seconds)", async () => {
                const count = await fetchFirmwareUpdatesCount();
                if (count == null) return "Not available outside the Hub shell.";
                setFirmware(count);
                return count === 0 ? "Firmware is up to date." : `${count} firmware update(s) available.`;
              })
            }
          />
          <RecipeButton recipe="firmware-update" label="Apply firmware updates" busy={busy} run={run} />
          <RecipeButton recipe="enroll-secureboot" label="Enroll Secure Boot key" busy={busy} run={run} />
          <RecipeButton recipe="device-info" label="Full device report" busy={busy} run={run} />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
