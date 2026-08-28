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
  fetchStarterPacks,
  type AppStoreSnapshot,
  type FamiliarApp,
  type AppImageEntry,
  type AppStreamApp,
  type StarterPack,
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
  const [catalogQuery, setCatalogQuery] = useState("");
  const [query, setQuery] = useState("");
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAppStoreSnapshot(), fetchStarterPacks(), fetchFamiliarApps(), fetchAppImages()]).then(([s, p, f, images]) => {
      if (!cancelled) {
        setSnapshot(s);
        setPacks(p);
        setFamiliar(f);
        setAppImages(images);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const q = catalogQuery.trim();
    if (q.length < 2) { setCatalog(null); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => searchAppStream(q).then((apps) => { if (!cancelled) setCatalog(apps); }), 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [catalogQuery]);

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

  const matches = useMemo(() => {
    if (!familiar) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return familiar.slice(0, 4);
    return familiar.filter((app) => app.windows_name.toLowerCase().includes(needle)).slice(0, 6);
  }, [familiar, query]);

  const live = snapshot !== null || packs !== null || familiar !== null || appImages !== null;
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
                        <span key={a.id} className={`pill ${a.selected ? "pill-ok" : "pill-dim"}`} title={a.description}>
                          {a.label}
                        </span>
                      ))}
                    </div>
                    <CommandLine
                      label="Install this pack"
                      command={installCommand(pack.apps.filter((a) => a.selected).map((a) => a.id))}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ marginTop: 22 }}>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Search Flathub</p>
            <input value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="Search apps…" style={{ marginTop: 8, width: "100%", maxWidth: 340, padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13 }} />
            {catalog && <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
              {catalog.map((app) => <div key={app.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
                <div style={{ flex: 1 }}><p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>{app.name}</p><p className="card-copy" style={{ margin: "2px 0 0", fontSize: 11 }}>{app.summary || app.id}</p></div>
                <button disabled={busy !== null} onClick={() => run(`install-${app.id}`, `Installing ${app.name}…`, () => install(app.id))} style={{ padding: "7px 14px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12.5 }}>{busy === `install-${app.id}` ? "Installing…" : "Install"}</button>
              </div>)}
              {catalog.length === 0 && <p className="card-copy" style={{ fontSize: 12 }}>No Flathub matches.</p>}
            </div>}
          </div>

          {appImages && appImages.length > 0 && <div style={{ marginTop: 22 }}>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>AppImages found</p>
            {appImages.map((app) => <div key={app.path} style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}><p className="card-copy" style={{ flex: 1, fontSize: 12, margin: 0 }}>{app.name} — {app.executable ? "ready to run" : "not executable yet"}</p>{app.executable && <button disabled={busy !== null} onClick={() => run(`launch-${app.path}`, `Launching ${app.name}…`, () => launchAppImage(app.path))} style={{ padding: "5px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 }}>Launch</button>}</div>)}
          </div>}
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
