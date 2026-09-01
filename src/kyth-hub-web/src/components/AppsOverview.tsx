import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  fetchAppStoreSnapshot,
  fetchFontsReady,
  fetchInstalledFlatpaks,
  fetchNetworkSummary,
  type AppStoreSnapshot,
  type InstalledFlatpak,
  type NetworkSummary,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

type AppsReadings = {
  snapshot: AppStoreSnapshot | null;
  installed: InstalledFlatpak[] | null;
  fonts: { ready: boolean; detail: string } | null;
  network: NetworkSummary | null;
};

const emptyReadings: AppsReadings = { snapshot: null, installed: null, fonts: null, network: null };

async function readApps(): Promise<AppsReadings> {
  const [snapshot, installed, fonts, network] = await Promise.all([
    fetchAppStoreSnapshot(),
    fetchInstalledFlatpaks(),
    fetchFontsReady(),
    fetchNetworkSummary(),
  ]);
  return { snapshot, installed, fonts, network };
}

function AppsCard({ icon, label, value, detail, good }: { icon: string; label: string; value: string; detail: string; good: boolean | null }) {
  const tone = good === null ? "apps-card-muted" : good ? "apps-card-ok" : "apps-card-warn";
  return <article className={`apps-overview-card ${tone}`}><div className="apps-card-top"><span className="apps-card-icon" aria-hidden="true">{icon}</span><span className="apps-card-label">{label}</span><span className="apps-status-dot" /></div><strong className="apps-card-value">{value}</strong><span className="apps-card-detail">{detail}</span></article>;
}

export function AppsOverview() {
  const [readings, setReadings] = useState<AppsReadings>(emptyReadings);
  const [loaded, setLoaded] = useState(false);
  const [, setSearchParams] = useSearchParams();
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    readApps().then((next) => {
      if (!cancelled) {
        setReadings(next);
        setLoaded(true);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const installedCount = readings.snapshot?.installedCount ?? readings.installed?.length ?? null;
  const updates = readings.snapshot?.updatesAvailable ?? null;
  const providers = readings.network?.cloudProviders.length ?? null;
  const hasReadings = Object.values(readings).some((value) => value !== null);

  function openSection(section: string) {
    setSearchParams({ section }, { replace: true });
    window.setTimeout(() => document.querySelector(".tab-nav")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  async function refresh(): Promise<string> {
    const next = await readApps();
    setReadings(next);
    setLoaded(true);
    return "Apps status refreshed.";
  }

  const appValue = installedCount === null ? "Checking…" : `${installedCount} installed`;
  const appDetail = installedCount === null ? "Your app library is being read." : "Search Flathub and manage applications from the App Store.";
  const updateValue = updates === null ? "Not checked" : updates === 0 ? "All current" : `${updates} ready`;
  const updateDetail = updates === null ? "App updates appear after the catalog is read." : updates === 0 ? "No Flatpak updates are waiting." : "Review and apply updates from the App Store.";
  const workValue = readings.fonts ? readings.fonts.ready ? "Ready" : "Needs setup" : "Checking…";
  const workDetail = readings.fonts?.detail || "Office fonts and workday tools are being checked.";
  const servicesValue = providers === null ? "Checking…" : providers === 0 ? "None connected" : `${providers} connected`;
  const servicesDetail = readings.network?.detail || "Cloud storage and VPN connections for your workspace.";

  return <section className="apps-overview" aria-label="Apps overview">
    <div className={`apps-hero ${loaded && hasReadings ? "apps-hero-live" : "apps-hero-muted"}`}><div><span className="apps-eyebrow">Software center</span><h1>Make this desktop yours</h1><p>Find trusted apps, keep them current, and set up the tools you use every day.</p></div><div className="apps-ready-chip"><span />{loaded && hasReadings ? "Ready to explore" : "Checking library"}</div></div>
    <div className="apps-overview-grid">
      <AppsCard icon="▦" label="App library" value={appValue} detail={appDetail} good={installedCount === null ? null : true} />
      <AppsCard icon="↓" label="App updates" value={updateValue} detail={updateDetail} good={updates === null ? null : updates === 0} />
      <AppsCard icon="✦" label="App source" value="Flathub" detail="Trusted Flatpak applications through the native catalog bridge." good={hasReadings ? true : null} />
      <AppsCard icon="Aa" label="Work setup" value={workValue} detail={workDetail} good={readings.fonts ? readings.fonts.ready : null} />
      <AppsCard icon="⌁" label="Connected services" value={servicesValue} detail={servicesDetail} good={providers === null ? null : providers > 0 || Boolean(readings.network?.vpnConnected)} />
    </div>
    <div className="apps-actions-card"><div><span className="apps-eyebrow">Start here</span><h2>Choose what you need</h2><p>Install an app or prepare your workday without leaving the Hub.</p></div><div className="apps-actions"><ActionButton label="Find apps" disabled={busy !== null} onClick={() => openSection("App Store")} /><ActionButton label="Set up work" disabled={busy !== null} onClick={() => openSection("Work Setup")} /><ActionButton label={busy === "apps-refresh" ? "Refreshing…" : "Refresh status"} disabled={busy !== null} onClick={() => void run("apps-refresh", "Refreshing Apps status…", refresh)} /></div></div>
    <ActionStatus status={status} />
  </section>;
}
