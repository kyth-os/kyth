import { useEffect, useMemo, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchAppStoreSnapshot, fetchAppImages, fetchFamiliarApps, searchAppStream,
  installFlatpak, fetchInstallStatus, launchAppImage, fetchInstalledFlatpaks,
  uninstallFlatpak, makeAppImageExecutable, importAppImage, fetchStarterPacks,
  fetchKaliStatus, fetchSecHostTools, createKaliBox, exportKaliApps,
  removeKaliBox, enterKaliTerminal, installSecHostTool, uninstallSecHostTool,
  launchSecHostTool, type AppStoreSnapshot, type FamiliarApp, type AppImageEntry,
  type AppStreamApp, type StarterPack, type InstalledFlatpak, type SecHostTool,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

type SectionRun = (id: string, pendingLabel: string, action: () => Promise<string>) => Promise<void>;
const secBtnStyle = { padding: "6px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 } as const;

function iconUrlFor(id: string): string {
  return `https://dl.flathub.org/repo/appstream/x86_64/icons/128x128/${id}.png`;
}

function initials(name: string, id: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length > 1) return `${words[0][0]}${words[1][0]}`.toUpperCase();
  return (words[0] || id).slice(0, 2).toUpperCase();
}

function AppIcon({ name, id, iconUrl }: { name: string; id: string; iconUrl?: string }) {
  const [failed, setFailed] = useState(false);
  const source = iconUrl || (id ? iconUrlFor(id) : "");
  return <div className="app-catalog-icon" aria-hidden="true">
    {!failed && source ? <img src={source} alt="" onError={() => setFailed(true)} /> : <span>{initials(name, id)}</span>}
  </div>;
}

type CardApp = { id: string; name: string; summary: string; icon_url?: string };

function AppCard({ app, installed, busy, onInstall, onUninstall }: {
  app: CardApp; installed: boolean; busy: string | null;
  onInstall: (app: CardApp) => void; onUninstall: (app: CardApp) => void;
}) {
  const actionId = `${installed ? "uninstall" : "install"}-${app.id}`;
  return <article className="app-catalog-card">
    <div className="app-catalog-card-top">
      <AppIcon name={app.name} id={app.id} iconUrl={app.icon_url} />
      <div className="app-catalog-card-heading"><h3>{app.name || app.id}</h3><span className="app-catalog-source">Flatpak · Flathub</span></div>
      {installed && <span className="pill pill-ok app-installed-pill">Installed</span>}
    </div>
    <p className="app-catalog-summary">{app.summary || "A trusted application for KythOS."}</p>
    <div className="app-catalog-card-footer"><span className="app-catalog-id">{app.id}</span>
      {installed ? <button className="app-action-button app-action-secondary" disabled={busy !== null} onClick={() => onUninstall(app)}>{busy === actionId ? "Removing…" : "Remove"}</button>
        : <button className="app-action-button app-action-primary" disabled={busy !== null} onClick={() => onInstall(app)}>{busy === actionId ? "Installing…" : "Install"}</button>}
    </div>
  </article>;
}

function KaliCard({ busy, run }: { busy: string | null; run: SectionRun }) {
  const [installed, setInstalled] = useState<boolean | null>(null);
  const [tier, setTier] = useState<"headless" | "default" | "everything">("headless");
  useEffect(() => { let cancelled = false; fetchKaliStatus().then((value) => { if (!cancelled) setInstalled(value); }); return () => { cancelled = true; }; }, []);
  async function refresh(): Promise<void> { setInstalled(await fetchKaliStatus()); }
  return <div className="app-special-card">
    <div className="app-special-heading"><div className="app-special-icon">K</div><div><p className="app-special-title">Kali Linux Toolbox</p><p className="app-special-copy">A ready-to-use security environment managed from Kyth Hub.</p></div>{installed != null && <span className={`pill ${installed ? "pill-ok" : "pill-dim"}`}>{installed ? "Installed" : "Not installed"}</span>}</div>
    {installed === false && <div className="app-special-controls"><div className="app-choice-row">{([ ["headless", "Headless", "~150 CLI tools"], ["default", "Default", "CLI + GUI tools"], ["everything", "Everything", "All available tools"] ] as const).map(([value, label, detail]) => <label key={value} className={`app-choice ${tier === value ? "app-choice-selected" : ""}`}><input type="radio" name="kali-tier" checked={tier === value} onChange={() => setTier(value)} /><span><strong>{label}</strong><small>{detail}</small></span></label>)}</div><button disabled={busy !== null} onClick={() => run("kali-create", "Creating Kali box…", async () => { const result = await createKaliBox(tier); await refresh(); return result; })} style={secBtnStyle}>{busy === "kali-create" ? "Creating…" : "Create toolbox"}</button></div>}
    {installed === true && <div className="app-special-actions"><button disabled={busy !== null} onClick={() => run("kali-enter", "Opening terminal…", enterKaliTerminal)} style={secBtnStyle}>{busy === "kali-enter" ? "Opening…" : "Launch terminal"}</button><button disabled={busy !== null} onClick={() => run("kali-export", "Exporting GUI apps…", exportKaliApps)} style={secBtnStyle}>{busy === "kali-export" ? "Exporting…" : "Export apps"}</button><button disabled={busy !== null} onClick={() => run("kali-remove", "Stopping and removing Kali box…", async () => { const result = await removeKaliBox(); await refresh(); return result; })} style={{ ...secBtnStyle, borderColor: "var(--danger, #c0392b)", color: "var(--danger, #c0392b)" }}>{busy === "kali-remove" ? "Removing…" : "Remove toolbox"}</button></div>}
  </div>;
}

function HostToolsGrid({ busy, run }: { busy: string | null; run: SectionRun }) {
  const [tools, setTools] = useState<SecHostTool[] | null>(null);
  useEffect(() => { let cancelled = false; fetchSecHostTools().then((value) => { if (!cancelled) setTools(value); }); return () => { cancelled = true; }; }, []);
  async function refresh(): Promise<void> { const fresh = await fetchSecHostTools(); if (fresh) setTools(fresh); }
  if (!tools || tools.length === 0) return null;
  return <div className="app-special-list"><p className="app-subsection-label">Host-side security tools</p><p className="app-subsection-copy">Native Flatpak tools with first-class Wayland integration.</p><div className="app-tool-grid">{tools.map((tool) => <div key={tool.flatpak} className="app-tool-card"><AppIcon name={tool.name} id={tool.flatpak} /><div className="app-tool-copy"><strong>{tool.name}</strong><span>{tool.desc}</span></div>{tool.installed ? <div className="app-tool-actions"><button disabled={busy !== null} onClick={() => run(`sec-launch-${tool.flatpak}`, `Launching ${tool.name}…`, () => launchSecHostTool(tool.flatpak))} style={secBtnStyle}>Launch</button><button disabled={busy !== null} onClick={() => run(`sec-uninstall-${tool.flatpak}`, `Uninstalling ${tool.name}…`, async () => { const result = await uninstallSecHostTool(tool.flatpak); await refresh(); return result; })} style={secBtnStyle}>Remove</button></div> : <button disabled={busy !== null} onClick={() => run(`sec-install-${tool.flatpak}`, `Installing ${tool.name}…`, async () => { const result = await installSecHostTool(tool.flatpak); await refresh(); return result; })} style={secBtnStyle}>Install</button>}</div>)}</div></div>;
}

// Apps is the KythOS software center: discovery and lifecycle actions stay
// behind typed Tauri commands, while this component only owns presentation.
export function AppStoreSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<AppStoreSnapshot | null>(null);
  const [packs, setPacks] = useState<StarterPack[] | null>(null);
  const [familiar, setFamiliar] = useState<FamiliarApp[] | null>(null);
  const [appImages, setAppImages] = useState<AppImageEntry[] | null>(null);
  const [catalog, setCatalog] = useState<AppStreamApp[] | null>(null);
  const [installed, setInstalled] = useState<InstalledFlatpak[] | null>(null);
  const [appImagePath, setAppImagePath] = useState("");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [catalogSearching, setCatalogSearching] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAppStoreSnapshot(), fetchStarterPacks(), fetchFamiliarApps(), fetchAppImages(), fetchInstalledFlatpaks()]).then(([s, p, f, images, apps]) => { if (!cancelled) { setSnapshot(s); setPacks(p); setFamiliar(f); setAppImages(images); setInstalled(apps); setLoaded(true); } });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    const q = catalogQuery.trim();
    if (q.length < 2) { setCatalog(null); setCatalogSearching(false); return; }
    let cancelled = false;
    const timer = window.setTimeout(async () => { setCatalogSearching(true); const apps = await searchAppStream(q); if (!cancelled) { setCatalog(apps ?? []); setCatalogSearching(false); } }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [catalogQuery]);
  async function refreshInstalled(): Promise<void> { const [nextSnapshot, nextInstalled] = await Promise.all([fetchAppStoreSnapshot(), fetchInstalledFlatpaks()]); if (nextSnapshot) setSnapshot(nextSnapshot); if (nextInstalled) setInstalled(nextInstalled); }
  async function install(id: string): Promise<string> { const job = await installFlatpak(id); for (let i = 0; i < 60; i += 1) { await new Promise((resolve) => window.setTimeout(resolve, 500)); const state = await fetchInstallStatus(job); if (!state || state.state === "running") continue; if (state.state === "complete") return state.detail; throw new Error(state.detail); } throw new Error("Installation is still running; refresh Apps in a moment."); }
  async function installPack(pack: StarterPack): Promise<string> { for (const app of pack.apps) await install(app.id); await refreshInstalled(); return `${pack.name} apps installed.`; }
  async function installAndRefresh(id: string): Promise<string> { const result = await install(id); await refreshInstalled(); return result; }

  const installedIds = useMemo(() => new Set((installed ?? []).map((app) => app.id)), [installed]);
  const featured = useMemo(() => { const seen = new Set<string>(); return (packs ?? []).flatMap((pack) => pack.apps.map((app) => ({ id: app.id, name: app.label, summary: app.description }))).filter((app) => { if (seen.has(app.id)) return false; seen.add(app.id); return true; }).slice(0, 8); }, [packs]);
  const familiarMatches = useMemo(() => { const needle = catalogQuery.trim().toLowerCase(); if (!needle || !familiar) return []; return familiar.filter((app) => app.windows_name.toLowerCase().includes(needle)).slice(0, 3); }, [catalogQuery, familiar]);
  const live = snapshot !== null || packs !== null || familiar !== null || appImages !== null || installed !== null;
  const onInstall = (app: CardApp) => { void run(`install-${app.id}`, `Installing ${app.name}…`, () => installAndRefresh(app.id)); };
  const onUninstall = (app: CardApp) => { void run(`uninstall-${app.id}`, `Removing ${app.name}…`, async () => { const result = await uninstallFlatpak(app.id); await refreshInstalled(); return result; }); };

  return <LiveSectionCard section={section} live={live}>
    {live ? <div className="app-store-content">
      <div className="app-store-hero"><div><span className="app-eyebrow">Kyth software center</span><h2>Find your next app</h2><p>Discover trusted Flatpaks, install them in one click, and keep your desktop organized from one place.</p></div><div className="app-store-hero-art"><span>✦</span><i /><i /><i /></div></div>
      <div className="app-store-search-wrap"><label htmlFor="app-store-search" className="app-search-label">Search applications</label><div className="app-store-search"><span aria-hidden="true">⌕</span><input id="app-store-search" value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="Search apps, tools, and games…" autoComplete="off" />{catalogQuery && <button className="app-search-clear" onClick={() => setCatalogQuery("")} aria-label="Clear app search">×</button>}</div><p className="app-search-hint">Searches the Flathub catalog through the native Kyth bridge.</p></div>
      <div className="app-stat-row"><div><span>Installed apps</span><strong>{snapshot?.installedCount ?? installed?.length ?? "—"}</strong></div><div><span>Updates ready</span><strong>{snapshot?.updatesAvailable ?? "—"}</strong></div><div><span>App source</span><strong>Flathub</strong></div></div>
      {catalogQuery.trim().length >= 2 ? <section className="app-catalog-section"><div className="app-section-heading"><div><span className="app-eyebrow">Discover</span><h2>Search results</h2></div>{catalog && <span className="app-result-count">{catalog.length} matches</span>}</div>{catalogSearching && <div className="app-loading-state"><span className="app-spinner" /> Searching Flathub…</div>}{!catalogSearching && catalog && <div className="app-card-grid">{catalog.map((app) => <AppCard key={app.id} app={app} installed={installedIds.has(app.id)} busy={busy} onInstall={onInstall} onUninstall={onUninstall} />)}</div>}{!catalogSearching && catalog?.length === 0 && <div className="app-empty-state"><strong>No apps found</strong><span>Try a broader search, or check the spelling.</span></div>}{familiarMatches.length > 0 && <div className="app-alternative-note"><strong>Looking for {familiarMatches[0].windows_name}?</strong><span>{familiarMatches[0].description}</span><button className="app-link-button" onClick={() => setCatalogQuery(familiarMatches[0].flatpak_id)}>View alternative</button></div>}</section> : <>
        <section className="app-catalog-section"><div className="app-section-heading"><div><span className="app-eyebrow">Curated for KythOS</span><h2>Popular apps</h2></div><span className="app-result-count">One-click install</span></div><div className="app-card-grid">{featured.map((app) => <AppCard key={app.id} app={app} installed={installedIds.has(app.id)} busy={busy} onInstall={onInstall} onUninstall={onUninstall} />)}</div></section>
        {packs && packs.length > 0 && <section className="app-catalog-section app-packs-section"><div className="app-section-heading"><div><span className="app-eyebrow">Get set up faster</span><h2>Starter collections</h2></div></div><div className="app-pack-grid">{packs.map((pack) => <article key={pack.name} className="app-pack-card"><div className="app-pack-art"><span>{pack.name.slice(0, 1)}</span><b /><b /><b /></div><div className="app-pack-body"><h3>{pack.name}</h3><p>{pack.desc}</p><div className="app-pack-apps">{pack.apps.map((app) => <span key={app.id} className={installedIds.has(app.id) ? "app-pack-app-installed" : ""}>{app.label}</span>)}</div><button className="app-action-button app-action-primary" disabled={busy !== null} onClick={() => void run(`pack-${pack.name}`, `Installing ${pack.name}…`, () => installPack(pack))}>{busy === `pack-${pack.name}` ? "Installing…" : "Install collection"}</button></div></article>)}</div></section>}
      </>}
      {installed && <section className="app-catalog-section"><div className="app-section-heading"><div><span className="app-eyebrow">Your library</span><h2>Installed on this device</h2></div><span className="app-result-count">{installed.length} apps</span></div>{installed.length > 0 ? <div className="app-card-grid">{installed.map((app) => <AppCard key={`${app.scope}:${app.id}`} app={{ id: app.id, name: app.name || app.id, summary: `${app.scope} install · ${app.version || "current"}`, icon_url: app.icon_url }} installed busy={busy} onInstall={onInstall} onUninstall={onUninstall} />)}</div> : <div className="app-empty-state"><strong>Your app library is empty</strong><span>Search above to install your first Flatpak.</span></div>}</section>}
      {appImages && appImages.length > 0 && <section className="app-secondary-section"><div className="app-section-heading"><div><span className="app-eyebrow">Other apps</span><h2>AppImages</h2></div><span className="app-result-count">{appImages.length} available</span></div><div className="app-image-grid">{appImages.map((app) => <article key={app.path} className="app-image-card"><AppIcon name={app.name} id="" /><div className="app-image-card-body"><strong>{app.name}</strong><span>{app.executable ? "Ready to launch" : "Needs permission before launch"}</span><small>{app.path}</small></div>{app.executable ? <button className="app-action-button app-action-secondary" disabled={busy !== null} onClick={() => void run(`launch-${app.path}`, `Launching ${app.name}…`, () => launchAppImage(app.path))}>Launch</button> : <button className="app-action-button app-action-primary" disabled={busy !== null} onClick={() => void run(`chmod-${app.path}`, `Making ${app.name} executable…`, async () => { const result = await makeAppImageExecutable(app.path); setAppImages((current) => current?.map((item) => item.path === app.path ? { ...item, executable: true } : item) ?? current); return result; })}>Make runnable</button>}</article>)}</div></section>}
      <section className="app-secondary-section"><div className="app-section-heading"><div><span className="app-eyebrow">Bring your own</span><h2>Import an AppImage</h2></div></div><p className="app-subsection-copy">Copy an AppImage from Downloads into your Applications folder and make it ready to run.</p><div className="app-import-row"><input value={appImagePath} onChange={(event) => setAppImagePath(event.target.value)} placeholder="/home/you/Downloads/app.AppImage" /><button className="app-action-button app-action-primary" disabled={busy !== null || !appImagePath.trim()} onClick={() => void run("import-appimage", "Importing AppImage…", async () => { const result = await importAppImage(appImagePath.trim()); setAppImagePath(""); const fresh = await fetchAppImages(); if (fresh) setAppImages(fresh); return result; })}>Import</button></div></section>
      <section className="app-secondary-section"><div className="app-section-heading"><div><span className="app-eyebrow">Advanced environments</span><h2>Specialized tools</h2></div></div><KaliCard busy={busy} run={run} /><HostToolsGrid busy={busy} run={run} /><div className="app-special-card app-dev-card"><p className="app-special-title">Developer and mobile environments</p><p className="app-special-copy">Set up optional Kyth development, AI, and Android tooling with native Hub actions.</p><div className="app-special-actions"><RecipeButton recipe="setup-kyth-dev-box" label="Kyth developer box" busy={busy} run={run} /><RecipeButton recipe="ai-dev-status" label="AI development status" busy={busy} run={run} /><RecipeButton recipe="ai-dev-setup" label="Set up AI development" busy={busy} run={run} /><RecipeButton recipe="setup-waydroid" label="Set up Waydroid" busy={busy} run={run} /><RecipeButton recipe="remove-waydroid" label="Remove Waydroid" busy={busy} run={run} /></div></div></section>
    </div> : <SectionFallbackNote loaded={loaded} />}
    <div className="app-footer-actions"><p className="app-subsection-copy">More KythOS applications</p><div className="app-special-actions"><RecipeButton recipe="install-vscode" label="VS Code" busy={busy} run={run} /><RecipeButton recipe="install-boxbuddy" label="BoxBuddy" busy={busy} run={run} /><RecipeButton recipe="install-jetbrains-toolbox" label="JetBrains Toolbox" busy={busy} run={run} /></div><ActionStatus status={status} /></div>
  </LiveSectionCard>;
}
