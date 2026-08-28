import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  commandText,
  fetchAuditCache,
  fetchGamingLibrary,
  fetchGamingSliceAvailable,
  fetchGamingSliceCommand,
  fetchProtonDbMany,
  fetchAntiCheatTable,
  type AntiCheatEntry,
  type ProtonDbResult,
  type AuditCache,
  type LauncherEntry,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, CommandLine, RecipeButton, useSectionAction } from "./SectionActions";

// "Play > Gaming" — audit master profile + live launcher library scan.
// Previously only audit pills; now also shows which launchers are installed
// and library counts, matching page_gaming_library.py's Steam/Heroic scan.
export function GamingSection({ section }: { section: HubSection }) {
  const launcherRecipes = [
    ["install-steam", "Steam"], ["install-heroic", "Heroic"], ["install-lutris", "Lutris"],
    ["install-bottles", "Bottles"], ["install-prismlauncher", "Prism Launcher"], ["install-itch", "Itch.io"],
    ["install-epic-launcher", "Epic Games"], ["install-battlenet", "Battle.net"], ["install-ea-app", "EA App"], ["install-ubisoft-connect", "Ubisoft Connect"],
  ] as const;
  const fixRecipes = [
    ["health-check", "Gaming health check"], ["preheat-shaders", "Preheat shaders"], ["enable-obs-capture", "Enable OBS capture"],
    ["game-boost", "Game boost"], ["controller-check", "Check controllers"], ["export-steam-games", "Export Steam library"],
  ] as const;
  const toolRecipes = [
    ["install-obs", "OBS Studio"], ["install-gpu-screen-recorder", "GPU Screen Recorder"],
    ["install-goverlay", "GOverlay"], ["install-mangojuice", "MangoJuice"], ["install-umu", "UMU"],
    ["install-lact", "LACT"], ["install-piper", "Piper"], ["install-solaar", "Solaar"],
  ] as const;
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [launchers, setLaunchers] = useState<LauncherEntry[] | null>(null);
  const [sliceAvailable, setSliceAvailable] = useState<boolean | null>(null);
  const [sliceCommand, setSliceCommand] = useState<string | null>(null);
  const [gameId, setGameId] = useState("");
  const [proton, setProton] = useState<ProtonDbResult[]>([]);
  const [antiCheat, setAntiCheat] = useState<AntiCheatEntry[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let c = false;
    Promise.all([
      fetchAuditCache(),
      fetchGamingLibrary(),
      fetchGamingSliceAvailable(),
      // Rendered as the string you paste into Steam's launch options, so
      // %command% is the argv placeholder rather than a real program.
      fetchGamingSliceCommand(["%command%"]).then(commandText),
      fetchAntiCheatTable(),
    ]).then(([a, l, avail, cmd, ac]) => {
      if (!c) {
        setAudit(a);
        setLaunchers(l);
        setSliceAvailable(avail);
        setSliceCommand(cmd);
        setAntiCheat(ac);
        setLoaded(true);
      }
    });
    return () => { c = true; };
  }, []);

  async function lookupProtonDb() {
    const ids = gameId.split(/[ ,]+/).map((id) => id.trim()).filter(Boolean).slice(0, 20);
    setProton((await fetchProtonDbMany(ids)) ?? []);
  }
  const live = audit !== null || launchers !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {audit ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Master profile</p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{String(audit.master ?? "unknown")}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
            {(["loader", "oom_gaming", "shader_tmpfs", "gaming_cfs", "ananicy", "kwin"] as const).map((k) => (
              <span key={k} className="pill pill-dim">{k}: {String(audit[k] ?? "\u2014")}</span>
            ))}
          </div>
          {launchers && launchers.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Launchers</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {launchers.map((l) => (
                  <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
                    <span className={`pill ${l.installed ? "pill-ok" : "pill-dim"}`}>{l.installed ? "installed" : "not installed"}</span>
                    <span style={{ fontWeight: 600 }}>{l.label}</span>
                    <span className="card-copy" style={{ fontSize: 12 }}>{l.library_count != null ? `${l.library_count} games` : l.path}</span>
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
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          <span className={`pill ${sliceAvailable ? "pill-ok" : "pill-dim"}`}>
            gaming slice: {sliceAvailable == null ? "unknown" : sliceAvailable ? "available" : "unavailable"}
          </span>
        </div>
        {sliceAvailable && (
          <CommandLine label="Steam launch options — runs the game in its own cgroup" command={sliceCommand} />
        )}
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>ProtonDB lookup</p>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input value={gameId} onChange={(event) => setGameId(event.target.value)} placeholder="Steam IDs, e.g. 730, 570" inputMode="numeric" style={{ flex: 1, maxWidth: 220, padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13 }} />
            <button disabled={!gameId.trim()} onClick={lookupProtonDb} style={{ padding: "7px 14px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600 }}>Look up</button>
          </div>
          {proton.length > 0 ? proton.map((result) => <p key={result.app_id} className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>{result.app_id}: {result.detail}</p>) : gameId && <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>Enter one or more Steam app IDs and look up current ProtonDB reports.</p>}
        </div>
        {antiCheat && <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Anti-cheat compatibility</p>
          {antiCheat.map((entry) => <div key={entry.game} style={{ display: "flex", gap: 8, marginTop: 8, fontSize: 12 }}><span className="pill pill-dim">{entry.status}</span><span><strong>{entry.game}</strong> — {entry.detail}</span></div>)}
        </div>}
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Migration checklist</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>Back up saves, install the launcher, verify each title in ProtonDB, then test controller and anti-cheat requirements before deleting the old install.</p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
          <RecipeButton recipe="gaming-mode" label="Switch to gaming mode" busy={busy} run={run} />
          <RecipeButton recipe="gaming-stack-status" label="Gaming stack status" busy={busy} run={run} />
        </div>
        <div style={{ marginTop: 22 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Gaming setup</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>Install a launcher or tool in its own terminal window. The recipe shows its own prompts and output.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            {launcherRecipes.map(([recipe, label]) => <RecipeButton key={recipe} recipe={recipe} label={label} busy={busy} run={run} />)}
          </div>
        </div>
        <div style={{ marginTop: 22 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Fixes and tools</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            {[...fixRecipes, ...toolRecipes].map(([recipe, label]) => <RecipeButton key={recipe} recipe={recipe} label={label} busy={busy} run={run} />)}
          </div>
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
