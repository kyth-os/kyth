import { useEffect, useMemo, useState } from "react";
import {
  fetchGuardianSnapshot, runGuardianCheck, waitGuardianCheck,
  fetchHardwareSnapshot, fetchStorageFree, fetchBootRuntimeChecks,
  fetchRecoveryStatus, fetchBtrfsHealth, fetchMemoryPressure,
  fetchDesktopStackChecks, fetchLoadedKernelModules, fetchKernelFlavor,
  type GuardianSnapshot, type HardwareSnapshot, type BootRuntimeCheck,
  type RecoveryStatus, type DesktopStackCheck,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

type MemoryReading = { status: string; detail: string };
type BtrfsReading = { status: string; detail: string };

type PcReadings = {
  guardian: GuardianSnapshot | null;
  hardware: HardwareSnapshot | null;
  storageFree: string | null;
  boot: BootRuntimeCheck[] | null;
  recovery: RecoveryStatus | null;
  btrfs: BtrfsReading | null;
  memory: MemoryReading | null;
  desktop: DesktopStackCheck[] | null;
  modules: string[] | null;
  kernel: string | null;
};

const emptyReadings: PcReadings = {
  guardian: null, hardware: null, storageFree: null, boot: null,
  recovery: null, btrfs: null, memory: null, desktop: null,
  modules: null, kernel: null,
};

async function readPc(): Promise<PcReadings> {
  const [guardian, hardware, storageFree, boot, recovery, btrfs, memory, desktop, modules, kernel] = await Promise.all([
    fetchGuardianSnapshot(), fetchHardwareSnapshot(), fetchStorageFree(), fetchBootRuntimeChecks(),
    fetchRecoveryStatus(), fetchBtrfsHealth(), fetchMemoryPressure(), fetchDesktopStackChecks(),
    fetchLoadedKernelModules(), fetchKernelFlavor(),
  ]);
  return { guardian, hardware, storageFree, boot, recovery, btrfs, memory, desktop, modules, kernel };
}

function tone(ok: boolean | null): string {
  return ok === null ? "this-pc-card-muted" : ok ? "this-pc-card-ok" : "this-pc-card-warn";
}

function InfoCard({ icon, label, value, detail, status }: {
  icon: string; label: string; value: string; detail: string; status?: boolean | null;
}) {
  return <article className={`this-pc-info-card ${tone(status ?? null)}`}>
    <div className="this-pc-card-top"><span className="this-pc-card-icon" aria-hidden="true">{icon}</span><span className="this-pc-card-label">{label}</span>{status !== undefined && <span className={`this-pc-status-dot ${status === null ? "this-pc-status-unknown" : status ? "this-pc-status-ok" : "this-pc-status-warn"}`} />}</div>
    <strong className="this-pc-card-value">{value}</strong>
    <span className="this-pc-card-detail">{detail}</span>
  </article>;
}

export function ThisPcOverview() {
  const [readings, setReadings] = useState<PcReadings>(emptyReadings);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    readPc().then((next) => { if (!cancelled) { setReadings(next); setLoaded(true); } });
    return () => { cancelled = true; };
  }, []);

  const bootPassed = readings.boot?.filter((check) => check.passed).length ?? null;
  const bootTotal = readings.boot?.length ?? null;
  const desktopPassed = readings.desktop?.filter((check) => check.passed && !check.advisory).length ?? null;
  const desktopTotal = readings.desktop?.filter((check) => !check.advisory).length ?? null;
  const pending = readings.guardian?.pending.length ?? 0;
  const bootHealthy = bootPassed !== null && bootTotal !== null ? bootPassed === bootTotal : null;
  const memoryHealthy = readings.memory ? readings.memory.status.toLowerCase() === "ok" : null;
  const overallHealthy = readings.guardian || readings.boot || readings.memory
    ? pending === 0 && (bootHealthy !== false) && (memoryHealthy !== false)
    : null;

  const healthDetail = useMemo(() => {
    if (!loaded) return "Reading Guardian and boot checks…";
    if (overallHealthy === null) return "Health readings are not available yet.";
    const parts = [`${pending} open recommendation${pending === 1 ? "" : "s"}`];
    if (bootPassed !== null && bootTotal !== null) parts.push(`${bootPassed}/${bootTotal} boot checks`);
    if (readings.memory) parts.push(`memory ${readings.memory.status}`);
    return overallHealthy ? parts.join(" · ") : `${parts.join(" · ")} · review needed`;
  }, [bootPassed, bootTotal, loaded, overallHealthy, pending, readings.memory]);

  async function refresh(): Promise<string> {
    const next = await readPc();
    setReadings(next);
    setLoaded(true);
    return "This PC status refreshed.";
  }

  async function guardianCheck(): Promise<string> {
    const job = await runGuardianCheck(false);
    await waitGuardianCheck(job);
    return await refresh();
  }

  const gpu = readings.hardware?.gpuName || (readings.hardware?.hasNvidia ? "NVIDIA graphics" : "Graphics not identified");
  const gpuDetail = readings.hardware
    ? `${readings.hardware.isHybrid ? "Hybrid graphics" : "Single GPU"} · ${readings.hardware.capabilities.length} capabilities`
    : "Hardware readings are not available yet.";
  const storageDetail = readings.btrfs?.detail || "Free space from the system storage volume.";
  const recovery = readings.recovery;
  const recoveryValue = recovery?.has_staged ? "Update staged" : recovery?.has_rollback ? "Rollback ready" : "Current system";
  const recoveryDetail = recovery
    ? `${recovery.has_staged ? "Reboot to apply" : "No staged update"} · ${recovery.has_rollback ? "rollback available" : "no rollback recorded"}`
    : "Recovery safeguards are not available yet.";
  const desktopValue = desktopPassed !== null && desktopTotal !== null ? `${desktopPassed}/${desktopTotal} checks` : "Not checked";
  const desktopHealthy = desktopPassed !== null && desktopTotal !== null ? desktopPassed === desktopTotal : null;
  const driverDetail = readings.modules ? `${readings.modules.length} tracked driver${readings.modules.length === 1 ? "" : "s"} loaded` : "Driver readings are not available yet.";

  return <section className="this-pc-overview" aria-label="This PC overview">
    <div className="this-pc-hero">
      <div><span className="this-pc-eyebrow">Device overview</span><h1>This PC at a glance</h1><p>System health, hardware, and recovery status in one place.</p></div>
      <div className={`this-pc-health-chip ${overallHealthy === false ? "this-pc-health-warn" : overallHealthy === true ? "this-pc-health-ok" : "this-pc-health-unknown"}`}><span className="this-pc-health-pulse" />{overallHealthy === true ? "System looks good" : overallHealthy === false ? "Needs attention" : "Status checking"}</div>
    </div>

    <div className="this-pc-info-grid">
      <InfoCard icon="✓" label="System health" value={overallHealthy === true ? "Healthy" : overallHealthy === false ? "Review needed" : "Checking…"} detail={healthDetail} status={overallHealthy} />
      <InfoCard icon="▦" label="Graphics" value={gpu} detail={gpuDetail} status={readings.hardware ? true : null} />
      <InfoCard icon="◒" label="Storage available" value={readings.storageFree || "Not read"} detail={storageDetail} status={readings.btrfs ? readings.btrfs.status.toLowerCase() === "ok" : null} />
      <InfoCard icon="↶" label="Recovery" value={recoveryValue} detail={recoveryDetail} status={recovery ? !recovery.quarantined_digest : null} />
      <InfoCard icon="⌁" label="Desktop session" value={desktopValue} detail={readings.desktop ? `${desktopTotal === desktopPassed ? "Desktop checks passed" : "Some checks need attention"}` : "Wayland and desktop readings are not available yet."} status={desktopHealthy} />
      <InfoCard icon="⌘" label="Kernel & drivers" value={readings.kernel || "Not identified"} detail={driverDetail} status={readings.kernel || readings.modules ? true : null} />
    </div>

    <div className="this-pc-actions-card"><div><span className="this-pc-eyebrow">Quick actions</span><h2>Keep your system in shape</h2><p>Run focused checks here; detailed controls are available below.</p></div><div className="this-pc-actions"><ActionButton label={busy === "pc-refresh" ? "Refreshing…" : "Refresh status"} disabled={busy !== null} onClick={() => void run("pc-refresh", "Refreshing This PC status…", refresh)} /><ActionButton label={busy === "pc-health" ? "Checking…" : "Run health check"} disabled={busy !== null} onClick={() => void run("pc-health", "Running Guardian health check…", guardianCheck)} /></div></div>
    <ActionStatus status={status} />
  </section>;
}
