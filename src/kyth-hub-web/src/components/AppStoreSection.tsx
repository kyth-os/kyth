import { useEffect, useMemo, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchAppStoreSnapshot,
  fetchFamiliarApps,
  fetchStarterPacks,
  type AppStoreSnapshot,
  type FamiliarApp,
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
  const [query, setQuery] = useState("");
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAppStoreSnapshot(), fetchStarterPacks(), fetchFamiliarApps()]).then(([s, p, f]) => {
      if (!cancelled) {
        setSnapshot(s);
        setPacks(p);
        setFamiliar(f);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const matches = useMemo(() => {
    if (!familiar) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return familiar.slice(0, 4);
    return familiar.filter((app) => app.windows_name.toLowerCase().includes(needle)).slice(0, 6);
  }, [familiar, query]);

  const live = snapshot !== null || packs !== null || familiar !== null;
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
