import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchCompatibilityGames,
  fetchHardwareSnapshot,
  fetchMesaOverlayDryRun,
  fetchMesaVersion,
  fetchMokStatus,
  fetchSecurebootState,
  type MokStatus,
  type CompatibilityGame,
  runPrivilegedAction,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

// "Play > Compatibility" — Secure Boot / anti-cheat readiness plus the
// Mesa version Proton actually runs against.
//
// Mount deliberately reads only cheap things: the disk-cached
// secureboot-state scalar, hardware-summary capabilities, and mesa_version
// (one rpm/glxinfo call). The two slow paths — mokutil, which takes a
// couple of seconds per invocation, and the Mesa overlay dry run — sit
// behind buttons so switching to this tab never stalls.
export function CompatibilitySection({ section }: { section: HubSection }) {
  const [sbState, setSbState] = useState<string | null>(null);
  const [mesa, setMesa] = useState<string | null>(null);
  const [mok, setMok] = useState<MokStatus | null>(null);
  const [hwCaps, setHwCaps] = useState<string[] | null>(null);
  const [games, setGames] = useState<CompatibilityGame[] | null>(null);
  const [gameFilter, setGameFilter] = useState<"all" | "works" | "tweaks" | "blocked">("all");
  const [gameQuery, setGameQuery] = useState("");
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let c = false;
    Promise.all([fetchSecurebootState(), fetchHardwareSnapshot(), fetchMesaVersion(), fetchCompatibilityGames()]).then(([sb, h, m, matrix]) => {
      if (!c) {
        setSbState(sb);
        setHwCaps(h?.capabilities ?? null);
        setMesa(m);
        setGames(matrix);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);

  const live = sbState !== null || hwCaps !== null || mesa !== null || games !== null;
  const visibleGames = (games ?? []).filter((game) => {
    const matchesFilter = gameFilter === "all"
      || (gameFilter === "works" && (game.status === "native" || game.status === "proton"))
      || game.status === gameFilter;
    return matchesFilter && game.name.toLowerCase().includes(gameQuery.trim().toLowerCase());
  });
  const workingGames = (games ?? []).filter((game) => game.status !== "blocked").length;
  const blockedGames = (games ?? []).filter((game) => game.status === "blocked").length;
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {sbState && (
              <span className={`pill ${sbState === "enabled" ? "pill-ok" : "pill-dim"}`}>Secure Boot: {sbState}</span>
            )}
            {mok && (
              <span className={`pill ${mok.enrolled === "enrolled" ? "pill-ok" : "pill-dim"}`}>MOK: {mok.enrolled}</span>
            )}
            {mesa && <span className="pill pill-dim">Mesa {mesa}</span>}
          </div>
          {hwCaps && hwCaps.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              {hwCaps.slice(0, 6).map((cap) => (
                <span key={cap} className="pill pill-dim">{cap}</span>
              ))}
            </div>
          )}
          {games && (
            <p className="card-copy" style={{ marginTop: 12, fontSize: 12 }}>
              {workingGames} of {games.length} listed titles are marked native, working, or tweakable; {blockedGames} are currently blocked by compatibility limits.
            </p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Known game matrix</p>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>
          The bundled matrix is a starting point, not a guarantee. Check the title’s current ProtonDB reports before migrating a competitive or recently updated game.
        </p>
        {games ? (
          <>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              {([ ["all", "All"], ["works", "Works"], ["tweaks", "Tweaks"], ["blocked", "Blocked"] ] as const).map(([value, label]) => (
                <button key={value} className="action-button" onClick={() => setGameFilter(value)} aria-pressed={gameFilter === value}>{label}</button>
              ))}
              <input
                value={gameQuery}
                onChange={(event) => setGameQuery(event.target.value)}
                placeholder="Filter titles"
                aria-label="Filter compatibility titles"
                style={{ minWidth: 150, flex: 1, maxWidth: 240, padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13 }}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
              {visibleGames.map((game) => {
                const label = game.status === "native" ? "Native" : game.status === "proton" ? "Works" : game.status === "tweaks" ? "Tweaks" : "Blocked";
                return (
                  <div key={game.name} style={{ padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <strong style={{ flex: 1 }}>{game.name}</strong>
                      <span className={`pill ${game.status === "blocked" ? "pill-dim" : game.status === "tweaks" ? "pill-warn" : "pill-ok"}`}>{label}</span>
                      {game.anticheat !== "None" && <span className="pill pill-dim">{game.anticheat}</span>}
                    </div>
                    <p className="card-copy" style={{ margin: "5px 0 0", fontSize: 12 }}>{game.note}</p>
                    {game.source_url && <a href={game.source_url} target="_blank" rel="noreferrer" className="card-copy" style={{ display: "inline-block", marginTop: 5, fontSize: 11 }}>Source: {game.source}</a>}
                  </div>
                );
              })}
              {visibleGames.length === 0 && <p className="card-copy" style={{ fontSize: 12 }}>No titles match this filter.</p>}
            </div>
          </>
        ) : (
          <SectionFallbackNote loaded={loaded} />
        )}
      </div>

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>How anti-cheat works on Linux</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
          {[
            ["Valve Anti-Cheat (VAC)", "ok", "Runs in user space; support is title-specific, so check the game’s current Steam notes."],
            ["Easy Anti-Cheat", "ok", "Linux support exists, but each developer must enable it. Kernel-mode configurations remain blocked."],
            ["BattlEye", "ok", "Some Proton titles work when the developer opts in; verify the specific title before migrating."],
            ["Vanguard / RICOCHET / Hyperion", "blocked", "Kernel-level Windows drivers do not have a Linux equivalent and these titles are currently unplayable here."],
          ].map(([name, statusText, detail]) => (
            <div key={name} style={{ padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
              <span className={`pill ${statusText === "blocked" ? "pill-dim" : "pill-ok"}`} style={{ marginRight: 8 }}>{statusText === "blocked" ? "Blocked" : "Title-dependent"}</span>
              <strong>{name}</strong>
              <p className="card-copy" style={{ margin: "5px 0 0", fontSize: 12 }}>{detail}</p>
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Windows compatibility apps</p>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>Use the Gaming page to install launchers. For standalone Windows installers, create a gaming bottle in Bottles and test one app at a time.</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 10 }}>
          {[ ["EA App", "Lutris", "Install through the EA App recipe."], ["Battle.net", "Lutris", "Install through the Battle.net recipe."], ["Ubisoft Connect", "Lutris", "Install through the Ubisoft Connect recipe."], ["Rockstar Launcher", "Bottles", "Create a gaming bottle and run the installer."], ["Vortex (Nexus)", "Bottles", "Create a gaming bottle; mod support varies by title."], ["GOG Galaxy", "Heroic", "Heroic is the preferred native library path."], ["Epic Games Store", "Heroic", "Heroic replaces the Epic launcher for most library workflows."], ["Xbox App", "Cloud", "Use Xbox Cloud Gaming; there is no native Linux client."] ].map(([name, tool, note]) => (
            <div key={name} style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap", padding: "7px 0", borderBottom: "1px solid var(--hairline)" }}>
              <strong style={{ minWidth: 145 }}>{name}</strong><span className="pill pill-dim">{tool}</span><span className="card-copy" style={{ fontSize: 12 }}>{note}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
          <a className="action-button" href="https://www.protondb.com" target="_blank" rel="noreferrer">Open ProtonDB</a>
          <a className="action-button" href="https://www.xbox.com/play" target="_blank" rel="noreferrer">Open Xbox Cloud Gaming</a>
        </div>
      </div>

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
          Anti-cheat in some games needs Secure Boot on with KythOS's key enrolled.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton
            label={busy === "mok" ? "Checking…" : "Check MOK enrollment"}
            disabled={busy !== null}
            onClick={() =>
              run("mok", "Asking mokutil… (this takes a few seconds)", async () => {
                const fresh = await fetchMokStatus();
                if (!fresh) return "Not available outside the Hub shell.";
                setMok(fresh);
                setSbState(fresh.sb_state);
                return `Secure Boot ${fresh.sb_state}, key ${fresh.enrolled}.`;
              })
            }
          />
          <ActionButton label={busy === "enroll" ? "Enrolling…" : "Enroll KythOS key"} disabled={busy !== null} onClick={() => run("enroll", "Enrolling KythOS Secure Boot key…", () => runPrivilegedAction("secureboot_enroll"))} />
          <ActionButton
            label={busy === "mesa" ? "Testing…" : "Test Mesa overlay"}
            disabled={busy !== null}
            onClick={() =>
              run("mesa", "Running the Mesa overlay dry run…", async () => {
                const res = await fetchMesaOverlayDryRun();
                if (!res) return "Not available outside the Hub shell.";
                return res.detail;
              })
            }
          />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
