import { useEffect, useMemo, useState } from "react";
import {
  fetchMigrationReadiness, fetchNtfsDrives, fetchNetworkSummary,
  fetchCloudOauthStatus, fetchConfiguredNetworkShares, fetchVpnSavedProfile,
  openMoveFilesApp, openCloudStorageApp, openNetworkSharesApp, openVpnApp,
  type MigrationReadiness, type NtfsDrive, type NetworkSummary,
  type ConfiguredNetworkShare, type VpnSavedProfile,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

type CloudStatus = { ok: boolean; detail: string };
type MoveReadings = {
  readiness: MigrationReadiness | null;
  drives: NtfsDrive[] | null;
  network: NetworkSummary | null;
  cloud: CloudStatus | null;
  shares: ConfiguredNetworkShare[] | null;
  vpnProfile: VpnSavedProfile | null;
};

const emptyReadings: MoveReadings = { readiness: null, drives: null, network: null, cloud: null, shares: null, vpnProfile: null };

async function readMoveIn(): Promise<MoveReadings> {
  const [readiness, drives, network, cloud, shares, vpnProfile] = await Promise.all([
    fetchMigrationReadiness(), fetchNtfsDrives(), fetchNetworkSummary(),
    fetchCloudOauthStatus(), fetchConfiguredNetworkShares(), fetchVpnSavedProfile(),
  ]);
  return { readiness, drives, network, cloud, shares, vpnProfile };
}

function MoveCard({ icon, label, value, detail, status }: { icon: string; label: string; value: string; detail: string; status?: boolean | null }) {
  const state = status === undefined || status === null ? "move-card-muted" : status ? "move-card-ok" : "move-card-warn";
  return <article className={`move-in-card ${state}`}>
    <div className="move-in-card-top"><span className="move-in-card-icon" aria-hidden="true">{icon}</span><span className="move-in-card-label">{label}</span>{status !== undefined && <span className={`this-pc-status-dot ${status === null ? "this-pc-status-unknown" : status ? "this-pc-status-ok" : "this-pc-status-warn"}`} />}</div>
    <strong className="move-in-card-value">{value}</strong>
    <span className="move-in-card-detail">{detail}</span>
  </article>;
}

export function MoveInOverview() {
  const [readings, setReadings] = useState<MoveReadings>(emptyReadings);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    readMoveIn().then((next) => { if (!cancelled) { setReadings(next); setLoaded(true); } });
    return () => { cancelled = true; };
  }, []);

  const ready = readings.readiness?.parity === "ok";
  const driveCount = readings.drives?.length ?? null;
  const bitlockerCount = readings.drives?.filter((drive) => drive.is_bitlocker).length ?? 0;
  const providerCount = readings.network?.cloudProviders.length ?? 0;
  const networkKnown = readings.network !== null;
  const vpnConnected = readings.network?.vpnConnected ?? null;
  const overallReady = readings.readiness || readings.drives || readings.network
    ? ready || (driveCount !== null && driveCount > 0)
    : null;

  const readinessDetail = useMemo(() => {
    if (!loaded) return "Checking Windows volumes and migration paths…";
    if (!readings.readiness) return "Migration readiness is not available yet.";
    return `Files ${readings.readiness.files} · bookmarks ${readings.readiness.bookmarks} · cloud ${readings.readiness.onedrive}`;
  }, [loaded, readings.readiness]);

  async function refresh(): Promise<string> {
    const next = await readMoveIn();
    setReadings(next);
    setLoaded(true);
    return "Move In status refreshed.";
  }

  const filesValue = driveCount === null ? "Not scanned" : driveCount === 0 ? "No Windows volume" : `${driveCount} Windows volume${driveCount === 1 ? "" : "s"}`;
  const filesDetail = driveCount === null ? "Drive detection has not completed yet." : bitlockerCount > 0 ? `${bitlockerCount} BitLocker volume${bitlockerCount === 1 ? "" : "s"} need unlocking` : "Ready to preview files and migration paths.";
  const cloudValue = providerCount > 0 ? `${providerCount} provider${providerCount === 1 ? "" : "s"} connected` : readings.cloud?.ok ? "Account ready" : "Not connected";
  const cloudDetail = readings.network?.cloudProviders.join(" · ") || readings.cloud?.detail || "Connect OneDrive, Google Drive, or Dropbox from Cloud Storage.";
  const shareCount = readings.shares?.length ?? readings.network?.smbMounts ?? null;
  const shareValue = shareCount === null ? "Not checked" : shareCount === 0 ? "No shares mounted" : `${shareCount} share${shareCount === 1 ? "" : "s"} available`;
  const vpnValue = vpnConnected === true ? `Connected${readings.network?.vpnName ? ` · ${readings.network.vpnName}` : ""}` : vpnConnected === false ? "Not connected" : "Not checked";
  const vpnDetail = readings.vpnProfile ? `Saved profile · ${readings.vpnProfile.gateway}` : "Use the VPN connection app for saved work profiles and sign-in.";

  return <section className="move-in-overview" aria-label="Move In overview">
    <div className="move-in-hero"><div><span className="move-in-eyebrow">Migration center</span><h1>Bring your digital life with you</h1><p>Move files, settings, accounts, and connected resources into KythOS from one place.</p></div><div className={`move-in-ready-chip ${overallReady === true ? "move-in-ready-ok" : overallReady === false ? "move-in-ready-warn" : "move-in-ready-unknown"}`}><span />{overallReady === true ? "Ready to move in" : overallReady === false ? "Needs preparation" : "Checking readiness"}</div></div>
    <div className="move-in-card-grid">
      <MoveCard icon="⇢" label="Migration readiness" value={overallReady === true ? "Ready" : overallReady === false ? "Needs preparation" : "Checking…"} detail={readinessDetail} status={overallReady} />
      <MoveCard icon="▤" label="Windows volumes" value={filesValue} detail={filesDetail} status={driveCount === null ? null : driveCount > 0} />
      <MoveCard icon="☁" label="Cloud storage" value={cloudValue} detail={cloudDetail} status={readings.network || readings.cloud ? providerCount > 0 || readings.cloud?.ok === true : null} />
      <MoveCard icon="▰" label="Network shares" value={shareValue} detail={networkKnown ? `${readings.network?.smbMounts ?? 0} currently mounted · ${readings.shares?.length ?? 0} saved` : "Share discovery is not available yet."} status={readings.network ? true : null} />
      <MoveCard icon="⌁" label="VPN connection" value={vpnValue} detail={vpnDetail} status={vpnConnected} />
    </div>
    <div className="move-in-actions-card"><div><span className="move-in-eyebrow">Start here</span><h2>Choose what to bring over</h2><p>Each workflow opens with a preview before anything is copied or changed.</p></div><div className="move-in-actions"><ActionButton label={busy === "open-files" ? "Opening…" : "Move files & settings"} disabled={busy !== null} onClick={() => void run("open-files", "Opening the migration workflow…", openMoveFilesApp)} /><ActionButton label={busy === "open-cloud" ? "Opening…" : "Connect cloud storage"} disabled={busy !== null} onClick={() => void run("open-cloud", "Opening Cloud Storage…", openCloudStorageApp)} /><ActionButton label={busy === "open-shares" ? "Opening…" : "Manage network shares"} disabled={busy !== null} onClick={() => void run("open-shares", "Opening Network Shares…", openNetworkSharesApp)} /><ActionButton label={busy === "open-vpn" ? "Opening…" : "Open VPN"} disabled={busy !== null} onClick={() => void run("open-vpn", "Opening VPN connection…", openVpnApp)} /><ActionButton label={busy === "move-refresh" ? "Refreshing…" : "Refresh status"} disabled={busy !== null} onClick={() => void run("move-refresh", "Refreshing Move In status…", refresh)} /></div></div>
    <ActionStatus status={status} />
  </section>;
}
