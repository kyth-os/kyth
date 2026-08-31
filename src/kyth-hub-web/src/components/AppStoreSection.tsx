import { useEffect, useMemo, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchAppStoreSnapshot,
  fetchAppImages,
  fetchFamiliarApps,
  searchAppStream,
  installFlatpak,
  fetchInstallStatus,
  launchAppImage,
  fetchInstalledFlatpaks,
  uninstallFlatpak,
  makeAppImageExecutable,
  importAppImage,
  fetchStarterPacks,
  type AppStoreSnapshot,
  type FamiliarApp,
  type AppImageEntry,
  type AppStreamApp,
  type StarterPack,
  type InstalledFlatpak,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, CommandLine, RecipeButton, useSectionAction } from "./SectionActions";

/** The command that installs a pack's preselected apps in one go. Shown
 * rather than spawned: there is no bridge command for it, and adding a
 * generic "run this argv" one would be a new privilege surface for a
 * string the frontend chose. */
function installCommand(ids: string[]): string | null {
  if (ids.length === 0) return null;
  return `flatpak install -y flathub ${ids.join(" ")}`;
}

// "Apps > App Store" — flatpak counts, the starter-pack catalog, and the
// "I used X on Windows" chooser (software_catalog.rs's familiar_apps).
export function AppStoreSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<AppStoreSnapshot | null>(null);
  const [packs, setPacks] = useState<StarterPack[] | null>(null);
  const [familiar, setFamiliar] = useState<FamiliarApp[] | null>(null);
  const [appImages, setAppImages] = useState<AppImageEntry[] | null>(null);
  const [catalog, setCatalog] = useState<AppStreamApp[] | null>(null);
  const [installed, setInstalled] = useState<InstalledFlatpak[] | null>(null);
  const [packSelections, setPackSelections] = useState<Record<string, string[]>>({});
  const [appImagePath, setAppImagePath] = useState("");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [catalogSearching, setCatalogSearching] = useState(false);
  const [query, setQuery] = useState("");
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAppStoreSnapshot(), fetchStarterPacks(), fetchFamiliarApps(), fetchAppImages(), fetchInstalledFlatpaks()]).then(([s, p, f, images, apps]) => {
      if (!cancelled) {
        setSnapshot(s);
        setPacks(p);
        setPackSelections(Object.fromEntries((p ?? []).map((pack) => [pack.name, pack.apps.filter((app) => app.selected).map((app) => app.id)])));
        setFamiliar(f);
        setAppImages(images);
        setInstalled(apps);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const q = catalogQuery.trim();
    if (q.length < 2) { setCatalog(null); setCatalogSearching(false); return; }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setCatalogSearching(true);
      const apps = await searchAppStream(q);
      if (!cancelled) {
        setCatalog(apps ?? []);
        setCatalogSearching(false);
      }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [catalogQuery]);

  async function refreshInstalled(): Promise<void> {
    const [nextSnapshot, nextInstalled] = await Promise.all([fetchAppStoreSnapshot(), fetchInstalledFlatpaks()]);
    if (nextSnapshot) setSnapshot(nextSnapshot);
    if (nextInstalled) setInstalled(nextInstalled);
  }

  async function install(id: string): Promise<string> {
    const job = await installFlatpak(id);
    for (let i = 0; i < 60; i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 500));
      const state = await fetchInstallStatus(job);
      if (!state || state.state === "running") continue;
      if (state.state === "complete") return state.detail;
      throw new Error(state.detail);
    }
    throw new Error("Installation is still running; check Flatpak in a moment.");
  }

  async function installPack(pack: StarterPack): Promise<string> {
    const ids = packSelections[pack.name] ?? [];
    if (ids.length === 0) throw new Error("Select at least one app first.");
    for (const id of ids) await install(id);
    await refreshInstalled();
    return `${pack.name} starter pack installed.`;
  }

  async function installAndRefresh(id: string): Promise<string> {
    const result = await install(id);
    await refreshInstalled();
    return result;
  }

  const matches = useMemo(() => {
    if (!familiar) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return familiar.slice(0, 4);
    return familiar.filter((app) => app.windows_name.toLowerCase().includes(needle)).slice(0, 6);
  }, [familiar, query]);

  const live = snapshot !== null || packs !== null || familiar !== null || appImages !== null || installed !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          {snapshot && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
              <div>
                <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Flatpaks installed</p>
                <p style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 800 }}>{snapshot.installedCount ?? "—"}</p>
              </div>
              <div>
                <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Updates available</p>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 22, fontWeight: 800 }}>{snapshot.updatesAvailable ?? "—"}</span>
                  {snapshot.updatesAvailable != null && (
                    <span className={`pill ${snapshot.updatesAvailable === 0 ? "pill-ok" : "pill-warn"}`}>
                      {snapshot.updatesAvailable === 0 ? "up to date" : "pending"}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {familiar && familiar.length > 0 && (
            <div style={{ marginTop: 22 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                What did you use on Windows?
              </p>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Photoshop, Office, Discord…"
                style={{
                  marginTop: 8,
                  width: "100%",
                  maxWidth: 340,
                  padding: "8px 12px",
                  borderRadius: 999,
                  border: "1px solid var(--hairline)",
                  background: "var(--card)",
                  fontSize: 13,
                }}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                {matches.map((app) => (
                  <div key={app.flatpak_id} style={{ padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
                    <p style={{ fontWeight: 700, fontSize: 13, margin: 0 }}>{app.windows_name}</p>
                    <p className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>{app.description}</p>
                    <CommandLine label={app.flatpak_id} command={installCommand([app.flatpak_id])} />
                  </div>
                ))}
                {matches.length === 0 && (
                  <p className="card-copy" style={{ fontSize: 12 }}>
                    Nothing in the built-in map matches “{query}” — search Discover for it instead.
                  </p>
                )}
              </div>
            </div>
          )}

          {packs && packs.length > 0 && (
            <div style={{ marginTop: 22 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Starter packs</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                {packs.map((pack) => (
                  <div key={pack.name} style={{ padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
                    <p style={{ fontWeight: 700, fontSize: 13, margin: 0 }}>{pack.name}</p>
                    <p className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>{pack.desc}</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {pack.apps.map((a) => (
                        <label key={a.id} className="pill pill-dim" title={a.description} style={{ cursor: "pointer" }}>
                          <input type="checkbox" checked={(packSelections[pack.name] ?? []).includes(a.id)} onChange={(event) => setPackSelections((current) => ({ ...current, [pack.name]: event.target.checked ? [...(current[pack.name] ?? []), a.id] : (current[pack.name] ?? []).filter((id) => id !== a.id) }))} /> {a.label}
                        </label>
                      ))}
                    </div>
                    <button disabled={busy !== null} onClick={() => run(`pack-${pack.name}`, `Installing ${pack.name}…`, () => installPack(pack))} style={{ marginTop: 10, padding: "6px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 }}>{busy === `pack-${pack.name}` ? "Installing…" : "Install selected"}</button>
                    <CommandLine
                      label="Install this pack"
                      command={installCommand((packSelections[pack.name] ?? []).map((id) => id))}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ marginTop: 22 }}>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Search Flathub</p>
            <input value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="Search apps…" style={{ marginTop: 8, width: "100%", maxWidth: 340, padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13 }} />
            {catalogSearching && <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>Searching Flathub…</p>}
            {catalog && <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
              {catalog.map((app) => <div key={app.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
                <div style={{ flex: 1 }}><p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>{app.name}</p><p className="card-copy" style={{ margin: "2px 0 0", fontSize: 11 }}>{app.summary || app.id}</p></div>
                <button disabled={busy !== null} onClick={() => run(`install-${app.id}`, `Installing ${app.name}…`, () => installAndRefresh(app.id))} style={{ padding: "7px 14px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12.5 }}>{busy === `install-${app.id}` ? "Installing…" : "Install"}</button>
              </div>)}
              {catalog.length === 0 && <p className="card-copy" style={{ fontSize: 12 }}>No Flathub matches.</p>}
            </div>}
          </div>

          {appImages && appImages.length > 0 && <div style={{ marginTop: 22 }}>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>AppImages found</p>
            {appImages.map((app) => <div key={app.path} style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}><p className="card-copy" style={{ flex: 1, fontSize: 12, margin: 0 }}>{app.name} — {app.executable ? "ready to run" : "not executable yet"}</p>{app.executable ? <button disabled={busy !== null} onClick={() => run(`launch-${app.path}`, `Launching ${app.name}…`, () => launchAppImage(app.path))} style={{ padding: "5px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 }}>Launch</button> : <button disabled={busy !== null} onClick={() => run(`chmod-${app.path}`, `Making ${app.name} executable…`, async () => { const result = await makeAppImageExecutable(app.path); setAppImages((current) => current?.map((item) => item.path === app.path ? { ...item, executable: true } : item) ?? current); return result; })} style={{ padding: "5px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 }}>Make executable</button>}</div>)}
          </div>}

          <div style={{ marginTop: 22 }}>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Import an AppImage</p>
            <p className="card-copy" style={{ fontSize: 12, marginTop: 5 }}>Enter a path from Downloads, Applications, or .local/bin. It is copied into Applications and made executable.</p>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <input value={appImagePath} onChange={(event) => setAppImagePath(event.target.value)} placeholder="/home/you/Downloads/app.AppImage" style={{ flex: 1, padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 12 }} />
              <button disabled={busy !== null || !appImagePath.trim()} onClick={() => run("import-appimage", "Importing AppImage…", async () => { const result = await importAppImage(appImagePath.trim()); setAppImagePath(""); const fresh = await fetchAppImages(); if (fresh) setAppImages(fresh); return result; })} style={{ padding: "7px 14px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 }}>Import</button>
            </div>
          </div>

          {installed && <div style={{ marginTop: 22 }}>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Installed Flatpaks</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 8 }}>
              {installed.map((app) => <div key={`${app.scope}:${app.id}`} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", border: "1px solid var(--hairline)", borderRadius: 9 }}><span style={{ flex: 1, fontSize: 12 }}><strong>{app.name || app.id}</strong><span className="card-copy"> — {app.id} · {app.scope}</span></span><button disabled={busy !== null} onClick={() => run(`uninstall-${app.scope}-${app.id}`, `Uninstalling ${app.name || app.id}…`, async () => { const result = await uninstallFlatpak(app.id); setInstalled((current) => current?.filter((item) => !(item.id === app.id && item.scope === app.scope)) ?? current); return result; })} style={{ padding: "5px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 }}>Uninstall</button></div>)}
              {installed.length === 0 && <p className="card-copy" style={{ fontSize: 12 }}>No installed Flatpak applications found.</p>}
            </div>
          </div>}

          <div style={{ marginTop: 22 }}>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Developer, creator, and specialized environments</p>
            <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>
              The old Hub grouped these tools separately from the general store. They remain opt-in recipes so the action and its system impact are visible before anything changes.
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <RecipeButton recipe="setup-kyth-dev-box" label="Set up Kyth developer box" busy={busy} run={run} />
              <RecipeButton recipe="ai-dev-status" label="AI development status" busy={busy} run={run} />
              <RecipeButton recipe="ai-dev-setup" label="Set up AI development" busy={busy} run={run} />
              <RecipeButton recipe="export-kali-apps" label="Export Kali apps" busy={busy} run={run} />
              <RecipeButton recipe="setup-waydroid" label="Set up Waydroid" busy={busy} run={run} />
              <RecipeButton recipe="remove-waydroid" label="Remove Waydroid" busy={busy} run={run} />
            </div>
            <CommandLine label="Kali environment (choose tools explicitly)" command="ujust setup-kali-box tools=headless" />
          </div>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
          Apps with a KythOS recipe install without needing a terminal.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <RecipeButton recipe="install-vscode" label="VS Code" busy={busy} run={run} />
          <RecipeButton recipe="install-boxbuddy" label="BoxBuddy" busy={busy} run={run} />
          <RecipeButton recipe="install-jetbrains-toolbox" label="JetBrains Toolbox" busy={busy} run={run} />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
